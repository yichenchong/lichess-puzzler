import csv

import chess
from chess.pgn import ChildNode

from retagger.model import Puzzle

if __name__=="__main__":
    # parser = argparse.ArgumentParser(prog='tagger.py', description='automatically tags lichess puzzles')
    # # read from file: non-optional
    # parser.add_argument("file", help="file to read from")
    # args = parser.parse_args()
    # file = args.file
    file = "C:\\Users\\liran\\OneDrive\\桌面\\lichess_db_puzzle.csv"

    # read csv file
    with open(file) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        header = next(csv_reader)
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
            break

