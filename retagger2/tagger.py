import csv
import time
from typing import Union, Tuple, List

import chess
from chess.pgn import ChildNode

from retagger2.model import Puzzle
from retagger2 import cook2 as cook


def make(id: str, fen: str, line: str) -> Puzzle:
    game = chess.pgn.Game()
    board = chess.Board(fen)
    game.setup(board)

    moves = line.split(' ')
    mainline = []
    for move in moves:
        mainline.append(chess.Move.from_uci(move))
    game.add_line(mainline)
    return Puzzle(id, game, 10000)


Tag = Union[Tuple[str, 'Tag'] | str | None]


def tag_to_str(tag: Tag):
    if isinstance(tag, str):
        return tag
    else:
        return tag_to_str(Tag[0]) + ":" + tag_to_str(Tag[1])


def tags_to_str(tags_list: List[Tag]):
    return " ".join([tag_to_str(tag) for tag in tags_list])


def full_tags_to_str(tags_list: List[List[Tag]]):
    return "/".join([tags_to_str(tag) for tag in tags_list])


if __name__ == "__main__":

    file = "lichess_db_puzzle.csv"

    # read old database in csv file
    with open(file) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        header = next(csv_reader)
        count = 1000
        start = time.process_time()
        # write updated tags to a new csv file
        with open("puzzles_updated_tag.csv", "w+", newline='') as new_file:
            writer = csv.writer(new_file)
            header[-1] = "hierarchy_tags"
            writer.writerow(header)
            for row in csv_reader:
                puzzle_id, fen, moves_str, *rest = row
                prev_themes = rest[4]
                game = chess.pgn.Game()
                board = chess.Board(fen)
                game.setup(board)

                mainline = [chess.Move.from_uci(move) for move in moves_str.split(' ')]
                game.add_line(mainline)

                cp_tag = "equality"
                if "mate" in prev_themes:
                    cp_tag = "mate"
                elif "crushing" in prev_themes:
                    cp_tag = "crushing"
                elif "advantage" in prev_themes:
                    cp_tag = "advantage"
                puzzle = Puzzle(puzzle_id, game, cp_tag)
                newTags = cook.cook(puzzle)
                row[-1] = full_tags_to_str(newTags)

                writer.writerow(row)

                count -= 1
                print(count)
                if count <= 0:
                    break
        time_elapsed = time.process_time() - start
        print(time_elapsed)
