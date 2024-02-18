from enum import Enum

from chess import Move


class PuzzleHeaders(Enum):
    id = 0
    fen = 1
    moves = 2
    themes = 7

class Puzzle:
    def __init__(self, row):
        self.id = row[PuzzleHeaders.id.value]
        self.fen = row[PuzzleHeaders.fen.value]
        self.moves = [Move.from_uci(m) for m in row[PuzzleHeaders.moves.value].split(" ")]
        self.tags = row[PuzzleHeaders.themes.value]
