import csv
import logging
import argparse
import time

import chess
import chess.pgn
import chess.engine
import copy
import sys
import util
import zstandard
from model import Puzzle, NextMovePair
from io import StringIO
from chess import Move, Color
from chess.engine import SimpleEngine, Mate, Cp, Score, PovScore
from chess.pgn import Game, ChildNode, GameNode
from typing import List, Optional, Union, Set
from util import get_next_move_pair, material_count, material_diff, is_up_in_material, maximum_castling_rights, win_chances, count_mates

version = 48

logger = logging.getLogger(__name__)
logger.setLevel(0)
logging.basicConfig(format='%(asctime)s %(levelname)-4s %(message)s', datefmt='%m/%d %H:%M')

pair_limit = chess.engine.Limit(depth=50, time=30, nodes=30_000_000)
mate_defense_limit = chess.engine.Limit(depth=15, time=10, nodes=10_000_000)

mate_soon = Mate(15)

class Regenerator:
    def __init__(self, engine: SimpleEngine):
        self.engine = engine

    def is_valid_mate_in_one(self, pair: NextMovePair) -> bool:
        if pair.best.score != Mate(1):
            return False
        non_mate_win_threshold = 0.6
        if not pair.second or win_chances(pair.second.score) <= non_mate_win_threshold:
            return True
        if pair.second.score == Mate(1):
            # if there's more than one mate in one, gotta look if the best non-mating move is bad enough
            logger.debug('Looking for best non-mating move...')
            mates = count_mates(copy.deepcopy(pair.node.board()))
            info = self.engine.analyse(pair.node.board(), multipv=mates + 1, limit=pair_limit)
            scores = [pv["score"].pov(pair.winner) for pv in info]
            # the first non-matein1 move is the last element
            if scores[-1] < Mate(1) and win_chances(scores[-1]) > non_mate_win_threshold:
                return False
            return True
        return False

    # is pair.best the only continuation?
    def is_valid_attack(self, pair: NextMovePair) -> bool:
        return (
                pair.second is None or
                self.is_valid_mate_in_one(pair) or
                win_chances(pair.best.score) > win_chances(pair.second.score) + 0.7
        )

    def get_next_pair(self, node: ChildNode, winner: Color) -> Optional[NextMovePair]:
        pair = get_next_move_pair(self.engine, node, winner, pair_limit)
        if node.board().turn == winner and not self.is_valid_attack(pair):
            logger.debug("No valid attack {}".format(pair))
            return None
        return pair

    def get_next_move(self, node: ChildNode, limit: chess.engine.Limit) -> Optional[Move]:
        result = self.engine.play(node.board(), limit=limit)
        return result.move if result else None

    def cook_mate(self, node: ChildNode, winner: Color) -> Optional[List[Move]]:

        board = node.board()

        if board.is_game_over():
            return []

        if board.turn == winner:
            pair = self.get_next_pair(node, winner)
            if not pair:
                return None
            if pair.best.score < mate_soon:
                logger.debug("Best move is not a mate, we're probably not searching deep enough")
                return None
            move = pair.best.move
        else:
            next = self.get_next_move(node, mate_defense_limit)
            if not next:
                return None
            move = next

        follow_up = self.cook_mate(node.add_main_variation(move), winner)

        if follow_up is None:
            return None

        return [move] + follow_up

    def cook_advantage(self, node: ChildNode, winner: Color, moves: [Move], compare_pos: int) -> Optional[List[NextMovePair]]:

        board = node.board()
        if compare_pos >= len(moves):
            return []

        if board.is_repetition(2):
            logger.debug("Found repetition, canceling")
            return None

        pair = self.get_next_pair(node, winner)
        if not pair:
            return []
        if pair.best.move != moves[compare_pos]:
            return None
        if pair.best.score < Cp(200):
            logger.debug("Not winning enough, aborting")
            return None

        follow_up = self.cook_advantage(node.add_main_variation(pair.best.move), winner, moves, compare_pos+1)

        if follow_up is None:
            return None

        return [pair] + follow_up

    def generate_new_puzzle(self, puzzle: Puzzle) -> Union[List[Puzzle], None]:
        # create list of potentially removable pieces
        # try removing each piece
        # test each piece with analyze_position
        # compare main lines with the resultant puzzles, if equal, add to the list
        # return the list
        puzzles = []
        current_board = puzzle.node.board()
        dict_of_pieces = current_board.piece_map(mask=chess.BB_ALL)
        is_previous_checked = current_board.is_check()

        for index, piece in dict_of_pieces.items():
            if piece.symbol() != "p" or chess.SQUARE_NAMES[index] != "e6":
                continue
            if piece.symbol() == 'K' or piece.symbol() == 'k' \
                    or index == puzzle.moves[0].from_square \
                    or index == puzzle.moves[0].to_square:
                continue
            new_board = current_board.copy()
            new_board.remove_piece_at(index)
            if new_board.is_checkmate() \
                    or new_board.is_stalemate() \
                    or (is_previous_checked and not new_board.is_check()) \
                    or (not is_previous_checked and new_board.is_check())\
                    or not new_board.is_legal(puzzle.moves[0]):
                continue
            print(chess.SQUARE_NAMES[index], piece)
            new_fen = new_board.fen()
            new_game = chess.pgn.Game()
            new_game.add_main_variation(puzzle.moves[0])
            new_game.setup(chess.Board(new_fen))
            info = self.engine.analyse(new_game.next().board(), chess.engine.Limit(depth=20))
            current_eval = info["score"]

            new_puzzle = self.analyze_position(new_game.next(), current_eval, puzzle.moves, tier=10)
            if isinstance(new_puzzle, Score):
                continue
            else:
                new_moves = new_puzzle.moves
                mainlines = puzzle.moves
                puzzles.append(new_puzzle)
        return puzzles

    def analyze_position(self, node: ChildNode, current_eval: PovScore, moves: [Move], tier: int) -> Union[Puzzle, Score]:

        board = node.board()
        winner = board.turn
        score = current_eval.pov(winner)
        if board.legal_moves.count() < 2:
            return score

        game_url = node.game().headers.get("Site")

        logger.debug("{} {} to {}".format(node.ply(), node.move.uci() if node.move else None, score))

        if is_up_in_material(board, winner):
            logger.debug("{} already up in material {} {} {}".format(node.ply(), winner, material_count(board, winner), material_count(board, not winner)))
            return score
        elif score >= Mate(1) and tier < 3:
            logger.debug("{} mate in one".format(node.ply()))
            return score
        elif score > mate_soon:
            logger.debug("Mate {}#{} Probing...".format(game_url, node.ply()))
            mate_solution = self.cook_mate(copy.deepcopy(node), winner)
            if mate_solution is None or (tier == 1 and len(mate_solution) == 3):
                return score
            return Puzzle(node, mate_solution, 999999999)
        elif score >= Cp(200): # and win_chances(score) > win_chances(prev_score) + 0.6:
            if score < Cp(400) and material_diff(board, winner) > -1:
                logger.debug("Not clearly winning and not from being down in material, aborting")
                return score
            logger.debug("Advantage {}# {} -> {}. Probing...".format(game_url, node.ply(), score))
            puzzle_node = copy.deepcopy(node)
            solution: Optional[List[NextMovePair]] = self.cook_advantage(puzzle_node, winner, moves, 1)
            if not solution:
                return score
            while len(solution) % 2 == 0 or not solution[-1].second:
                if not solution[-1].second:
                    logger.debug("Remove final only-move")
                solution = solution[:-1]
            if not solution or len(solution) == 1:
                logger.debug("Discard one-mover")
                return score
            if tier < 3 and len(solution) == 3:
                logger.debug("Discard two-mover")
                return score
            cp = solution[len(solution) - 1].best.score.score()
            return Puzzle(node, [p.best.move for p in solution], 999999998 if cp is None else cp)
        else:
            return score


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='Regenerator.py',
        description='takes a pgn file and produces chess puzzles')
    parser.add_argument("--file", "-f", help="input PGN file", required=True, metavar="FILE.pgn")
    parser.add_argument("--engine", "-e", help="analysis engine", default="./stockfish")
    parser.add_argument("--threads", "-t", help="count of cpu threads for engine searches", default="4")
    parser.add_argument("--url", "-u", help="URL where to post puzzles", default="http://localhost:8000")
    parser.add_argument("--token", help="Server secret token", default="changeme")
    parser.add_argument("--skip", help="How many games to skip from the source", default="0")
    parser.add_argument("--verbose", "-v", help="increase verbosity", action="count")
    parser.add_argument("--parts", help="how many parts", default="8")
    parser.add_argument("--part", help="which one of the parts", default="0")

    return parser.parse_args()


def make_engine(executable: str, threads: int) -> SimpleEngine:
    engine = SimpleEngine.popen_uci(executable)
    engine.configure({'Threads': threads})
    return engine


def open_file(file: str):
    if file.endswith(".zst"):
        return zstandard.open(file, "rt")
    return open(file)

def main(file, lines):
    engine = SimpleEngine.popen_uci(r"C:\Users\wangh\Downloads\stockfish-windows-x86-64-avx2\stockfish\stockfish-windows-x86-64-avx2.exe")
    regenerator = Regenerator(engine)
    count = 0
    with open(file) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        next(csv_reader)
        for row in csv_reader:
            id = row[0]
            if id != "000hf":
                continue
            fen = row[1]
            moves = [Move.from_uci(move) for move in row[2].split(" ")]
            board = chess.Board(fen)
            game = chess.pgn.Game()
            game.setup(board)
            puzzle = Puzzle(game, moves, 988888888888)
            start = time.time()
            anrs = regenerator.generate_new_puzzle(puzzle)
            end = time.time()
            print("-----------------------")
            print(f"Now is the {row}th puzzle")
            print("The time used is: ", end - start)
            print("the size of the generated new puzzles is: ", len(anrs))
            print(anrs)

            count += 1
            if count >= lines:
                break

if __name__ == "__main__":
    main(r"C:\Users\wangh\Downloads\lichess_db_puzzle\lichess_db_puzzle.csv", 100)

