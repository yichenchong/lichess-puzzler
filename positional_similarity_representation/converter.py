import time

import argparse
import chess
from chess import Board, SQUARE_NAMES, square_distance, SquareSet
from chess.pgn import Game
from positional_similarity_representation.models import Puzzle
import csv


def encode_board(board: Board):
    # Naive Encoding
    square_pos = " ".join(map(lambda s: s[1].symbol() + SQUARE_NAMES[s[0]], board.piece_map().items()))
    # Reachable Squares
    reachable_squares = []

    def move_to_weighted_str(move):
        mf = move.from_square
        mt = move.to_square
        d = square_distance(mf, mt)
        w = 1 - (7 * d / 64)
        p = board.piece_at(mf).symbol()
        encoded = f"{p}{SQUARE_NAMES[mt]}|{w:.2f}"
        reachable_squares.append(encoded)

    two_sided_moves = list(board.pseudo_legal_moves)
    oppboard = board.copy()
    oppboard.turn = chess.WHITE if board.turn == chess.BLACK else chess.BLACK
    two_sided_moves.extend(list(oppboard.pseudo_legal_moves))
    for move in two_sided_moves:
        move_to_weighted_str(move)
    reachable_squares_list = " ".join(reachable_squares)
    # Connectivity: Attacking and Defending Squares
    attacks = []
    defenses = []
    for square, piece in board.piece_map().items():
        attackers = board.attackers(piece.color, square)
        for attacker in attackers:
            attacks.append(f"{board.piece_at(attacker).symbol()}>{piece.symbol()}{SQUARE_NAMES[square]}")
        defenders = board.attackers(not piece.color, square)
        for defender in defenders:
            defenses.append(f"{board.piece_at(defender).symbol()}<{piece.symbol()}{SQUARE_NAMES[square]}")
    attacks_list = " ".join(attacks)
    defenses_list = " ".join(defenses)
    # Ray Attacks
    ray_attacks = []
    for square, piece in board.piece_map().items():
        sq = chess.SQUARES[square]
        moves = chess.SquareSet.from_square(sq)
        if piece.piece_type in [chess.BISHOP, chess.QUEEN]:
            if sq & chess.BB_CORNERS:
                moves |= (chess.BB_CORNERS
                          & (chess.BB_DARK_SQUARES if (sq & chess.BB_DARK_SQUARES) else chess.BB_LIGHT_SQUARES))
            elif sq & chess.BB_FILE_A:
                moves |= chess.SquareSet.ray(sq, chess.square(1, chess.square_rank(sq) - 1))
                moves |= chess.SquareSet.ray(sq, chess.square(1, chess.square_rank(sq) + 1))
            elif sq & chess.BB_RANK_1:
                moves |= chess.SquareSet.ray(sq, chess.square(chess.square_file(sq) - 1, 1))
                moves |= chess.SquareSet.ray(sq, chess.square(chess.square_file(sq) + 1, 1))
            else:
                moves |= chess.SquareSet.ray(sq, chess.square(chess.square_file(sq) - 1, chess.square_rank(sq) - 1))
                moves |= chess.SquareSet.ray(sq, chess.square(chess.square_file(sq) - 1, chess.square_rank(sq) + 1))
        if piece.piece_type in [chess.ROOK, chess.QUEEN]:
            moves |= chess.SquareSet.ray(
                sq, chess.square(chess.square_file(sq), 0 if chess.square_rank(sq) == 7 else 7))
            moves |= chess.SquareSet.ray(
                sq, chess.square(0 if chess.square_file(sq) == 7 else 7, chess.square_rank(sq)))
        for move in moves:
            if board.piece_at(move) and board.piece_at(move).color != piece.color and not board.attacks(sq) & move:
                ray_attacks.append(f"{piece.symbol()}={board.piece_at(move).symbol()}{SQUARE_NAMES[move]}")
    ray_attacks_list = " ".join(ray_attacks)
    return "\n".join([square_pos, reachable_squares_list, attacks_list, defenses_list, ray_attacks_list])


def convert(puzzle: Puzzle):
    # convert puzzle to representation
    board = Board(puzzle.fen)
    game = Game()
    game.setup(board)
    game.add_line(puzzle.moves)
    encoding = [encode_board(board)]
    for move in game.mainline():
        encoding.append(encode_board(move.board()))
    return encoding


def main(file, num_rows=None):
    # TO REMOVE
    row_count = 0
    # read csv file
    with open(file) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        next(csv_reader)
        for row in csv_reader:
            puzzle = Puzzle(row)
            reprs = convert(puzzle)
            for mn, rep in enumerate(reprs):
                with open(f"out/{puzzle.id}-{mn}", "w+") as f:
                    f.write(rep)
            # TO REMOVE
            row_count += 1
            if num_rows is not None and row_count >= num_rows:
                break
    return time.process_time()

if __name__ == "__main__":
    # parser = argparse.ArgumentParser(prog='tagger.py', description='automatically tags lichess puzzles')
    # # read from file: non-optional
    # parser.add_argument("file", help="file to read from")
    # args = parser.parse_args()
    # file = args.file
    file = "lichess_db_puzzle.csv"
    main(file, num_rows=10000)

