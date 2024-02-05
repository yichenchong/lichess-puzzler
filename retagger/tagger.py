import csv
import time

import chess
from chess.pgn import ChildNode

from retagger.model import Puzzle
from retagger.util import tag_distance, compute_similarity, search_similar_puzzle
from retagger import cook


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
            writer.writerow(header)
            for row in csv_reader:
                id = row[0]
                fen = row[1]
                game = chess.pgn.Game()
                board = chess.Board(fen)
                game.setup(board)
                moves = row[2].split(' ')

                parent = game
                mainline = []
                for move in moves:
                    mainline.append(chess.Move.from_uci(move))
                game.add_line(mainline)

                cp = 10
                puzzle = Puzzle(id, game, cp)
                newTags = cook.cook(puzzle)
                row[-3] = " ".join(newTags)

                writer.writerow(row[:-1])

                count -= 1
                if count <= 0:
                    break
        time_elapsed = time.process_time() - start
        print(time_elapsed)

    # search in updated database for most similar puzzles
    example_puzzle = make("2xWu3",
                       "rn3rk1/ppp2ppp/8/2b1N3/2Bqn1P1/3p4/PPP3PP/RNBQR2K w - - 1 12",
                       "c1e3 d4e3 e1e3 e4f2 h1g1 f2d1")
    t = cook.cook(example_puzzle)

    file = "puzzles_updated_tag.csv"

    # generate list of id and list of tags for search_similar_puzzle
    with open(file) as search_file:
        csv_reader = csv.reader(search_file, delimiter=',')
        header = next(csv_reader)
        count = 1000
        puzzles = []

        for row in csv_reader:
            tags = row[-2]
            puzzle_id = row[0]
            tags_list = tags.split(' ')
            print("tags_list = ", tags_list)
            puzzles.append((puzzle_id, tags_list))
            count -= 1

            if count <= 0:
                break
    print("base tag:", t)

    # search and output
    print(search_similar_puzzle(t, puzzles))
