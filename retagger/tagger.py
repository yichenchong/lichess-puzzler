import csv
import time

import chess
from chess.pgn import ChildNode

import cook
from retagger.model import Puzzle

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
    file = "C:\\Users\\liran\\OneDrive\\桌面\\lichess_db_puzzle.csv"

    # read csv file
    with open(file) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        header = next(csv_reader)
        count = 100000
        start = time.process_time()
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
            # print(",".join(row))

            count -= 1
            if count <= 0:
                break
        time_elapsed = time.process_time() - start
        print(time_elapsed)



            # testPuzzle = make("yUM8F",
            # "r1bq1rk1/ppp1bppp/2n2n2/4p1B1/4N1P1/3P1N1P/PPP2P2/R2QKB1R w KQ - 1 9",
            # "d1d2 f6e4 d3e4 c6d4 e1c1 d4f3 d2d8 e7g5 d8g5 f3g5")
            # print(cook.cook(testPuzzle))
            # break
