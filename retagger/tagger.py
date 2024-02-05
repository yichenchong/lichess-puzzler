import csv
import time

import chess
from chess.pgn import ChildNode

from retagger.model import Puzzle
from retagger.util import tag_distance, compute_similarity
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

if __name__=="__main__":
    # parser = argparse.ArgumentParser(prog='tagger.py', description='automatically tags lichess puzzles')
    # # read from file: non-optional
    # parser.add_argument("file", help="file to read from")
    # args = parser.parse_args()
    # file = args.file
    file = "lichess_db_puzzle.csv"


    # read csv file
    with open(file) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        header = next(csv_reader)
        count = 1000
        start = time.process_time()
        # write updated tags to the csv file
        with open("puzzles_updated_tag.csv", "w+", newline='') as new_file:
            writer = csv.writer(new_file)
            writer.writerow(header)
            for row in csv_reader:
                print(row)
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






