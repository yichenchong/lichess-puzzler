from dataclasses import dataclass, field
from chess.pgn import Game, ChildNode
from chess import Color
from typing import List, Literal, Optional

TagKind = Literal[
    "advancedPawn",
    "advantage",
    "anastasiaMate",
    "arabianMate",
    "attackingF2F7",
    "attraction",
    "backRankMate",
    "bishopEndgame",
    "bodenMate",
    "capturingDefender",
    "castling",
    "clearance",
    "coercion",
    "crushing",
    "defensiveMove",
    "discoveredAttack",
    "deflection",
    "doubleBishopMate",
    "doubleCheck",  # has multiple layers
    "dovetailMate",
    "equality",
    "enPassant",
    "exposedKing",
    "fork",  # has multiple layers
    "hangingPiece",
    "hookMate",
    "interference",
    "intermezzo",
    "kingsideAttack",
    "knightEndgame",
    "long",
    "mate",
    "mateIn5",
    "mateIn4",
    "mateIn3",
    "mateIn2",
    "mateIn1",
    "oneMove",
    "overloading",
    "pawnEndgame",
    "pin",   # has multiple layers
    "promotion",
    "queenEndgame",
    "queensideAttack",
    "quietMove",
    "rookEndgame",
    "queenRookEndgame",
    "sacrifice",    # has multiple layers
    "short",
    "simplification",
    "skewer",      # has multiple layers
    "smotheredMate",
    "trappedPiece",
    "underPromotion",
    "veryLong",
    "xRayAttack",   # has multiple layers
    "zugzwang"
]

@dataclass
class Puzzle:
    id: str
    game: Game
    pov: Color = field(init=False)
    mainline: List[ChildNode] = field(init=False)
    cp_tag: str

    def __post_init__(self):
        self.pov = not self.game.turn()
        self.mainline = list(self.game.mainline())
