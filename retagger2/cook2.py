from typing import List, Union, Optional, Tuple

import chess
from chess import PIECE_SYMBOLS, SquareSet, KING, PAWN, Color, QUEEN, ROOK, KNIGHT, BISHOP, square_file, square_rank
from chess.pgn import ChildNode

from retagger2.model import Puzzle
from retagger2.model import TagKind
from retagger2 import util
from retagger2.util import possible_exposed_king


Tag = Union[Tuple[str, 'Tag'] | str | None]


def cook(puzzle: Puzzle) -> List[List[Tag]]:
    puzzle_tags = []
    move_tags = []
    # move tags
    all_move_checks = [
        advanced_pawn, double_check, sacrifice, x_ray, fork, hanging_piece, trapped_piece, discovered_attack,
        discovered_check, quiet_move, defensive_move, attraction, deflection, skewer, interference,
        intermezzo, pin_prevents_attack, pin_prevents_escape, clearance, en_passant, castling, promotion,
        under_promotion,
        capturing_defender, attacking_f2_f7, exposed_king
    ]

    def move_tactic_check(node: ChildNode, checker: callable):
        tag = checker(node)
        if tag is not None:
            move_tags[-1].append(tag)

    for ply_no, node in enumerate(puzzle.mainline[1::2]):
        move_tags.append([])
        list(map(lambda f: move_tactic_check(node, f), all_move_checks))
        move_tags[-1].sort()

    # puzzle tags
    if puzzle.game.end().board().is_checkmate():  # rating difference and mate tags
        puzzle_tags.append("mate")
        puzzle_tags.append("mateIn" + str(len(puzzle.mainline) // 2))
        for mate_classifier in [
            smothered_mate, back_rank_mate, anastasia_mate, hook_mate, arabian_mate,
            boden_or_double_bishop_mate, dovetail_mate
        ]:
            mt = mate_classifier(puzzle)
            if mt is not None:
                puzzle_tags.append(mt)
                break
    elif puzzle.cp_tag == "crushing":
        puzzle_tags.append("crushing")
    elif puzzle.cp_tag == "advantage":
        puzzle_tags.append("advantage")
    else:
        puzzle_tags.append("equality")

    for piece in [PAWN, QUEEN, ROOK, BISHOP, KNIGHT]:
        if piece_endgame(puzzle, piece):
            puzzle_tags.append(PIECE_SYMBOLS[piece] + "Endgame")
            break
    else:
        if queen_rook_endgame(puzzle):
            puzzle_tags.append("queenRookEndgame")

    # side attack tags
    has_fork = False
    for move in move_tags:
        for t in move:
            if t.startswith("fork"):
                has_fork = True
                break

    if "backRankMate" not in puzzle_tags and not has_fork:
        if kingside_attack(puzzle):
            puzzle_tags.append("kingsideAttack")
        elif queenside_attack(puzzle):
            puzzle_tags.append("queensideAttack")

    # puzzle length tags
    if len(puzzle.mainline) == 2:
        puzzle_tags.append("oneMove")
    elif len(puzzle.mainline) == 4:
        puzzle_tags.append("short")
    elif len(puzzle.mainline) >= 8:
        puzzle_tags.append("veryLong")
    else:
        puzzle_tags.append("long")
    puzzle_tags.sort()

    move_tags.append(puzzle_tags)
    return move_tags


# helper functions
def pov_from_node(node: ChildNode) -> Color:
    return not node.turn()


def is_last_player_move(node: ChildNode) -> bool:
    return pov_from_node(node.root()) != node.turn() and (node.is_end() or node.next().is_end())


def is_first_player_move(node: ChildNode) -> bool:
    return pov_from_node(node.root()) != node.turn() and (
        node.parent == node.root() or node.parent.parent == node.root())


# tactics

def advanced_pawn(node: ChildNode) -> Optional[str]:
    if util.is_very_advanced_pawn_move(node):
        return "advancedPawn"
    return None


def double_check(node: ChildNode) -> Optional[str]:
    if len(node.board().checkers()) > 1:
        pieces = [node.board().piece_at(square).symbol() for square in node.board().checkers()]
        pieces.sort()
        pieces = ','.join(pieces)
        tag = "doubleCheck:" + pieces
        return tag
    return None


def sacrifice(node: ChildNode) -> Optional[str]:  # run from [1:]
    if is_first_player_move(node):
        return None
    # down in material compared to initial position, after moving
    root = node.root()
    initial = util.material_diff(root.next().board(), pov_from_node(node))
    last_d = util.material_diff(node.parent.parent.board(), pov_from_node(node))
    d = util.material_diff(node.board(), pov_from_node(node))
    has_promotion = False
    for n in root.mainline():
        if pov_from_node(node) == n.turn() and n.parent.parent is not None and n.parent.parent != root and \
            n.move.promotion:
            has_promotion = True
            break
    if d - last_d <= -2 and d - initial <= -2 and not has_promotion:
        piece = node.parent.parent.board().piece_at(node.parent.move.to_square).symbol().lower()
        return "sacrifice:" + piece
    return None


def x_ray(node: ChildNode) -> Optional[str]:  # run from [1:]
    if is_first_player_move(node) or not util.is_capture(node):
        return None
    prev_op_node = node.parent
    assert isinstance(prev_op_node, ChildNode)
    if prev_op_node.move.to_square != node.move.to_square or util.moved_piece_type(prev_op_node) == KING:
        return None
    prev_pl_node = prev_op_node.parent
    assert isinstance(prev_pl_node, ChildNode)
    if prev_pl_node.move.to_square != prev_op_node.move.to_square:
        return None
    if prev_op_node.move.from_square in SquareSet.between(node.move.from_square, node.move.to_square):
        piece = util.moved_piece_type(node)
        return "xRay:" + PIECE_SYMBOLS[piece]
    return None


def fork(node: ChildNode) -> Optional[str]:
    if util.moved_piece_type(node) is KING:
        return None
    board = node.board()
    if util.is_in_bad_spot(board, node.move.to_square):
        return None
    nb = 0
    for (piece, square) in util.attacked_opponent_squares(board, node.move.to_square, pov_from_node(node)):
        if piece.piece_type == PAWN:
            continue
        if (
            util.king_values[piece.piece_type] > util.king_values[util.moved_piece_type(node)] or (
            util.is_hanging(board, piece, square) and
            square not in board.attackers(node.turn(), node.move.to_square)
        )
        ):
            nb += 1
    if nb > 1:
        piece = util.moved_piece_type(node)
        return "fork:" + PIECE_SYMBOLS[piece]


def hanging_piece(node: ChildNode) -> Optional[str]:  # run [0] only
    if not is_first_player_move(node):
        return None
    mainline0 = node.root().next()
    mainline1 = mainline0.next()
    to = mainline1.move.to_square
    captured = mainline0.board().piece_at(to)
    if mainline0.board().is_check() and (not captured or captured.piece_type == PAWN):
        return None
    if captured and captured.piece_type != PAWN:
        if util.is_hanging(mainline0.board(), captured, to):
            op_move = mainline0.move
            op_capture = node.root().board().piece_at(op_move.to_square)
            if op_capture and \
                    util.values[op_capture.piece_type] >= util.values[captured.piece_type] and op_move.to_square == to:
                return None
            puzzle_length = 0
            for _ in node.root().mainline():
                puzzle_length += 1
            if puzzle_length < 4:
                return "hangingPiece"
            board3 = node.root().next().next().next().next().board()
            if util.material_diff(board3, pov_from_node(node)) >= util.material_diff(
                mainline1.board(), pov_from_node(node)):
                return "hangingPiece"
    return None


def trapped_piece(node: ChildNode) -> Optional[str]:  # run for [1:]
    if is_first_player_move(node):
        return None
    square = node.move.to_square
    captured = node.parent.board().piece_at(square)
    if captured and captured.piece_type != PAWN:
        prev = node.parent
        assert isinstance(prev, ChildNode)
        if prev.move.to_square == square:
            square = prev.move.from_square
        if util.is_trapped(prev.parent.board(), square):
            return "trappedPiece"
    return None


def discovered_attack(node: ChildNode) -> Optional[str]:  # run for [1:]
    if is_first_player_move(node):
        return None
    if discovered_check(node):
        return "discoveredAttack"

    if util.is_capture(node):
        between = SquareSet.between(node.move.from_square, node.move.to_square)
        assert isinstance(node.parent, ChildNode)
        if node.parent.move.to_square == node.move.to_square:
            return None
        prev = node.parent.parent
        assert isinstance(prev, ChildNode)
        if (
            prev.move.from_square in between and
            node.move.to_square != prev.move.to_square and
            node.move.from_square != prev.move.to_square and
            not util.is_castling(prev)
        ):
            return "discoveredAttack"
    return None


def discovered_check(node: ChildNode) -> Optional[str]:  # run for all
    board = node.board()
    checkers = board.checkers().copy()
    if checkers and node.move.to_square not in checkers:
        return "discoveredCheck:" + PIECE_SYMBOLS[board.piece_at(checkers.pop()).piece_type]
    return None


def quiet_move(node: ChildNode) -> Optional[str]:  # run for [:-1]
    if is_last_player_move(node):
        return None
    return "quietMove:" + node.board().piece_at(node.move.to_square).symbol() if (
        # no check given or escaped
        not node.board().is_check() and not node.parent.board().is_check() and
        # no capture made or threatened
        not util.is_capture(node) and not util.attacked_opponent_pieces(node.board(), node.move.to_square,
                                                                        pov_from_node(node)) and
        # no advanced pawn push
        not util.is_advanced_pawn_move(node) and
        util.moved_piece_type(node) != KING
    ) else None


def defensive_move(node: ChildNode) -> Optional[str]:
    if (
        node.is_end() and node.parent.board().legal_moves.count() >= 3 and
        not node.board().is_check() and not util.is_capture(node) and not util.is_advanced_pawn_move and
        not util.attacked_opponent_pieces(node.board(), node.move.to_square, pov_from_node(node))
    ):
        # like quiet_move, but on last move
        # at least 3 legal moves
        # no check given, no piece taken
        # no advanced pawn push
        return "defensiveMove:" + PIECE_SYMBOLS[util.moved_piece_type(node)]
    if node.board().is_check() or util.is_capture(node) or node.parent.board().legal_moves.count() < 3:
        return None
    return "defensiveMove:" + PIECE_SYMBOLS[util.moved_piece_type(node)] if node.parent.board().is_check() else None


def attraction(node: ChildNode) -> Optional[str]:
    if is_last_player_move(node):
        return None
    # 1. player moves to a square
    first_move_to = node.move.to_square
    opponent_reply = node.next()
    # 2. opponent captures on that square
    if opponent_reply and opponent_reply.move.to_square == first_move_to:
        attracted_piece = util.moved_piece_type(opponent_reply)
        if attracted_piece in [KING, QUEEN, ROOK]:
            attracted_to_square = opponent_reply.move.to_square
            next_node = util.next_node(opponent_reply)
            if next_node:
                attackers = next_node.board().attackers(pov_from_node(node), attracted_to_square)
                # 3. player attacks that square
                if next_node.move.to_square in attackers:
                    # 4. player checks on that square
                    if attracted_piece == KING:
                        return "attraction"
                    n3 = util.next_next_node(next_node)
                    # 4. or player later captures on that square
                    if n3 and n3.move.to_square == attracted_to_square:
                        return "attraction"
    return None


def deflection(node: ChildNode) -> Optional[str]:
    if is_first_player_move(node):
        return None
    captured_piece = node.parent.board().piece_at(node.move.to_square)
    if captured_piece or node.move.promotion:
        capturing_piece = util.moved_piece_type(node)
        if captured_piece and util.king_values[captured_piece.piece_type] > util.king_values[capturing_piece]:
            return None
        square = node.move.to_square
        prev_op_move = node.parent.move
        assert prev_op_move
        grandpa = node.parent.parent
        assert isinstance(grandpa, ChildNode)
        prev_player_move = grandpa.move
        prev_player_capture = grandpa.parent.board().piece_at(prev_player_move.to_square)
        if (
            (not prev_player_capture or util.values[prev_player_capture.piece_type] < util.moved_piece_type(grandpa))
            and square != prev_op_move.to_square and square != prev_player_move.to_square and
            (prev_op_move.to_square == prev_player_move.to_square or grandpa.board().is_check()) and
            (
                square in grandpa.board().attacks(prev_op_move.from_square) or
                node.move.promotion and
                square_file(node.move.to_square) == square_file(prev_op_move.from_square) and
                node.move.from_square in grandpa.board().attacks(prev_op_move.from_square)
            ) and square not in node.parent.board().attacks(prev_op_move.to_square)
        ):
            return "deflection"
    return None


def exposed_king(node: ChildNode) -> Optional[str]:
    if not possible_exposed_king(node.root().next().board(), pov_from_node(node)) or \
        is_first_player_move(node) or is_last_player_move(node):
        return None
    if node.board().is_check():
        return "exposedKing"
    return None


def skewer(node: ChildNode) -> Optional[str]:
    prev = node.parent
    assert isinstance(prev, ChildNode)
    capture = prev.board().piece_at(node.move.to_square)
    if capture and util.moved_piece_type(node) in util.ray_piece_types and not node.board().is_checkmate():
        between = SquareSet.between(node.move.from_square, node.move.to_square)
        op_move = prev.move
        assert op_move
        if op_move.to_square == node.move.to_square or op_move.from_square not in between:
            return None
        if (
            util.king_values[util.moved_piece_type(prev)] > util.king_values[capture.piece_type] and
            util.is_in_bad_spot(prev.board(), node.move.to_square)
        ):
            piece = util.moved_piece_type(node)
            return "skewer:" + PIECE_SYMBOLS[piece]
    return None


def interference(node: ChildNode) -> Optional[str]:
    # self interference
    prev_board = node.parent.board()
    square = node.move.to_square
    capture = prev_board.piece_at(square)
    if is_first_player_move(node) or not capture or not util.is_hanging(prev_board, capture, square):
        return None
    grandpa = node.parent.parent
    assert grandpa
    init_board = grandpa.board()
    defenders = init_board.attackers(capture.color, square)
    defender = defenders.pop() if defenders else None
    defender_piece = init_board.piece_at(defender) if defender else None
    if defender and defender_piece and defender_piece.piece_type in util.ray_piece_types and \
        node.parent.move and node.parent.move.to_square in SquareSet.between(square, defender):
        return "interference"
    # interference
    if square != node.parent.move.to_square and node.parent.parent and node.parent.parent.parent:
        init_board = node.parent.parent.parent.board()
        defenders = init_board.attackers(capture.color, square)
        defender = defenders.pop() if defenders else None
        defender_piece = init_board.piece_at(defender) if defender else None
        interfering = node.parent.parent
        if defender and defender_piece and defender_piece.piece_type in util.ray_piece_types and \
            interfering.move and interfering.move.to_square in SquareSet.between(square, defender):
            return "interference"
    return None


def intermezzo(node: ChildNode) -> Optional[str]:
    if not util.is_capture(node) or is_first_player_move(node):
        return None
    capture_move = node.move
    capture_square = node.move.to_square
    op_node = node.parent
    assert isinstance(op_node, ChildNode)
    prev_pov_node = node.parent.parent
    assert isinstance(prev_pov_node, ChildNode)
    prev_op_node = prev_pov_node.parent
    assert isinstance(prev_op_node, ChildNode)
    if op_node.move.from_square not in prev_pov_node.board().attackers(not pov_from_node(node), capture_square) and \
        prev_pov_node.move.to_square != capture_square and prev_op_node.move.to_square == capture_square and \
        util.is_capture(prev_op_node) and capture_move in prev_op_node.board().legal_moves:
        return "intermezzo"
    return None


def pin_prevents_attack(node: ChildNode) -> Optional[str]:
    board = node.board()
    for square, piece in board.piece_map().items():
        if piece.color == pov_from_node(node) or not board.is_pinned(piece.color, square):
            continue
        pin_dir = board.pin(piece.color, square)
        for attack in board.attacks(square):
            attacked = board.piece_at(attack)
            if attacked and attacked.color == pov_from_node(node) and attack not in pin_dir and (
                util.values[attacked.piece_type] > util.values[piece.piece_type] or
                util.is_hanging(board, attacked, attack)
            ):
                # find the piece doing the pinning
                possible_pinning_piece_type = None
                for possible_pinning_piece in board.attackers(pov_from_node(node), square):
                    if (possible_pinning_piece in pin_dir and possible_pinning_piece != square and
                        board.piece_at(possible_pinning_piece).piece_type in util.ray_piece_types):
                        possible_pinning_piece_type = board.piece_at(possible_pinning_piece).piece_type
                if possible_pinning_piece_type:
                    return "pin:preventsAttack:" + PIECE_SYMBOLS[possible_pinning_piece_type]


def pin_prevents_escape(node: ChildNode) -> Optional[str]:
    board = node.board()
    for pinned_square, pinned_piece in board.piece_map().items():
        if pinned_piece.color == pov_from_node(node) or not board.is_pinned(pinned_piece.color, pinned_square):
            continue
        pin_dir = board.pin(pinned_piece.color, pinned_square)
        for attacker_square in board.attackers(pov_from_node(node), pinned_square):
            if attacker_square in pin_dir:
                attacker = board.piece_at(attacker_square)
                assert attacker
                if util.values[pinned_piece.piece_type] > util.values[attacker.piece_type] or (
                    util.is_hanging(board, pinned_piece, pinned_square) and
                    pinned_square not in board.attackers(not pov_from_node(node), attacker_square) and
                    [m for m in board.pseudo_legal_moves if
                     m.from_square == pinned_square and m.to_square not in pin_dir]
                ):
                    return "pin:preventsEscape:" + attacker.symbol().lower()
    return None


def kingside_attack(puzzle: Puzzle) -> bool:
    return side_attack(puzzle, 7, [6, 7], 20)


def queenside_attack(puzzle: Puzzle) -> bool:
    return side_attack(puzzle, 0, [0, 1, 2], 18)


def side_attack(puzzle: Puzzle, corner_file: int, king_files: List[int], nb_pieces: int) -> bool:
    back_rank = 7 if puzzle.pov else 0
    init_board = puzzle.mainline[0].board()
    king_square = init_board.king(not puzzle.pov)
    if (
        not king_square or
        chess.square_rank(king_square) != back_rank or
        square_file(king_square) not in king_files or
        len(init_board.piece_map()) < nb_pieces or  # no endgames
        not any(node.board().is_check() for node in puzzle.mainline[1::2])
    ):
        return False
    score = 0
    corner = chess.square(corner_file, back_rank)
    for node in puzzle.mainline[1::2]:
        corner_dist = chess.square_distance(corner, node.move.to_square)
        if node.board().is_check():
            score += 1
        if util.is_capture(node) and corner_dist <= 3:
            score += 1
        elif corner_dist >= 5:
            score -= 1
    return score >= 2


def clearance(node: ChildNode) -> Optional[str]:  # will be marked on the move that the clearance sacrifice was made for
    if is_first_player_move(node):
        return None
    board = node.board()
    piece = board.piece_at(node.move.to_square)
    assert isinstance(node.parent, ChildNode)
    prev = node.parent.parent
    assert prev
    prev_move = prev.move
    assert prev_move
    return "clearance" if (
        not node.parent.board().piece_at(node.move.to_square) and  # not a capture
        piece and piece.piece_type in util.ray_piece_types and  # a sliding piece
        not prev_move.promotion and  # previous player move was not a promotion
        prev_move.to_square != node.move.from_square and  # previous player move did not move the piece
        prev_move.to_square != node.move.to_square and  # not executing a trade
        not node.parent.board().is_check() and  # player was not moving out of check
        (not board.is_check() or util.moved_piece_type(node.parent) != KING) and  # not putting the opponent in check
        (prev_move.from_square == node.move.to_square or  # previous player move was to make way for the piece
         prev_move.from_square in SquareSet.between(node.move.from_square, node.move.to_square)) and
        # previous player move was not a capture or previous player move was to a bad spot
        (prev.parent and not prev.parent.board().piece_at(prev_move.to_square) or
         util.is_in_bad_spot(prev.board(), prev_move.to_square))
    ) else None


def en_passant(node: ChildNode) -> Optional[str]:
    return "enPassant" if (util.moved_piece_type(node) == PAWN and
                           square_file(node.move.from_square) != square_file(node.move.to_square) and
                           not node.parent.board().piece_at(node.move.to_square)
                           ) else None


def castling(node: ChildNode) -> Optional[str]:
    return "castling" if util.is_castling(node) else None


def promotion(node: ChildNode) -> Optional[str]:
    return "promotion" if node.move.promotion else None


def under_promotion(node: ChildNode) -> Optional[str]:
    return "underPromotion" if node.move.promotion and (
        (node.board().is_checkmate() and node.move.promotion == KNIGHT) or \
        (not node.board().is_checkmate() and node.move.promotion != QUEEN)) else None


def capturing_defender(node: ChildNode) -> Optional[str]:
    if is_first_player_move(node):
        return None
    board = node.board()
    capture = node.parent.board().piece_at(node.move.to_square)
    assert isinstance(node.parent, ChildNode)
    if board.is_checkmate() or (
        capture and
        util.moved_piece_type(node) != KING and
        util.values[capture.piece_type] <= util.values[util.moved_piece_type(node)] and
        util.is_hanging(node.parent.board(), capture, node.move.to_square) and
        node.parent.move.to_square != node.move.to_square
    ):
        prev = node.parent.parent
        assert isinstance(prev, ChildNode)
        if not prev.board().is_check() and prev.move.to_square != node.move.from_square:
            assert prev.parent
            init_board = prev.parent.board()
            defender_square = prev.move.to_square
            defender = init_board.piece_at(defender_square)
            if (
                defender and
                defender_square in init_board.attackers(defender.color, node.move.to_square) and
                not init_board.is_check()
            ):
                return "capturingDefender"
    return None


def back_rank_mate(puzzle: Puzzle) -> Optional[str]:
    node = puzzle.game.end()
    board = node.board()
    king = board.king(not puzzle.pov)
    assert king is not None
    assert isinstance(node, ChildNode)
    back_rank = 7 if puzzle.pov else 0
    if board.is_checkmate() and square_rank(king) == back_rank:
        squares = SquareSet.from_square(king + (-8 if puzzle.pov else 8))
        if puzzle.pov:
            if chess.square_file(king) < 7:
                squares.add(king - 7)
            if chess.square_file(king) > 0:
                squares.add(king - 9)
        else:
            if chess.square_file(king) < 7:
                squares.add(king + 9)
            if chess.square_file(king) > 0:
                squares.add(king + 7)
        for square in squares:
            piece = board.piece_at(square)
            if piece is None or piece.color == puzzle.pov or board.attackers(puzzle.pov, square):
                return None
        return "backRankMate" if any(square_rank(checker) == back_rank for checker in board.checkers()) else None
    return None


def anastasia_mate(puzzle: Puzzle) -> Optional[str]:
    node = puzzle.game.end()
    board = node.board()
    king = board.king(not puzzle.pov)
    assert king is not None
    assert isinstance(node, ChildNode)
    if square_file(king) in [0, 7] and square_rank(king) not in [0, 7]:
        if square_file(node.move.to_square) == square_file(king) and util.moved_piece_type(node) in [QUEEN, ROOK]:
            if square_file(king) != 0:
                board.apply_transform(chess.flip_horizontal)
            king = board.king(not puzzle.pov)
            assert king is not None
            blocker = board.piece_at(king + 1)
            if blocker is not None and blocker.color != puzzle.pov:
                knight = board.piece_at(king + 3)
                if knight is not None and knight.color == puzzle.pov and knight.piece_type == KNIGHT:
                    return "anastasiaMate"
    return None


def hook_mate(puzzle: Puzzle) -> Optional[str]:
    node = puzzle.game.end()
    board = node.board()
    king = board.king(not puzzle.pov)
    assert king is not None
    assert isinstance(node, ChildNode)
    if util.moved_piece_type(node) == ROOK and chess.square_distance(node.move.to_square, king) == 1:
        for rook_defender_square in board.attackers(puzzle.pov, node.move.to_square):
            defender = board.piece_at(rook_defender_square)
            if defender and defender.piece_type == KNIGHT and chess.square_distance(rook_defender_square, king) == 1:
                for knight_defender_square in board.attackers(puzzle.pov, rook_defender_square):
                    pawn = board.piece_at(knight_defender_square)
                    if pawn and pawn.piece_type == PAWN:
                        return "hookMate"
    return None


def arabian_mate(puzzle: Puzzle) -> Optional[str]:
    node = puzzle.game.end()
    board = node.board()
    king = board.king(not puzzle.pov)
    assert king is not None
    assert isinstance(node, ChildNode)
    if square_file(king) in [0, 7] and square_rank(king) in [0, 7] and util.moved_piece_type(node) == ROOK and \
        chess.square_distance(node.move.to_square, king) == 1:
        for knight_square in board.attackers(puzzle.pov, node.move.to_square):
            knight = board.piece_at(knight_square)
            if knight and knight.piece_type == KNIGHT and (
                abs(square_rank(knight_square) - square_rank(king)) == 2 and
                abs(square_file(knight_square) - square_file(king)) == 2
            ):
                return "arabianMate"
    return None


def boden_or_double_bishop_mate(puzzle: Puzzle) -> Optional[TagKind]:
    node = puzzle.game.end()
    board = node.board()
    king = board.king(not puzzle.pov)
    assert king is not None
    assert isinstance(node, ChildNode)
    bishop_squares = list(board.pieces(BISHOP, puzzle.pov))
    if len(bishop_squares) < 2:
        return None
    for square in [s for s in SquareSet(chess.BB_ALL) if chess.square_distance(s, king) < 2]:
        if not all([p.piece_type == BISHOP for p in util.attacker_pieces(board, puzzle.pov, square)]):
            return None
    if (square_file(bishop_squares[0]) < square_file(king)) == (square_file(bishop_squares[1]) > square_file(king)):
        return "bodenMate"
    else:
        return "doubleBishopMate"


def dovetail_mate(puzzle: Puzzle) -> Optional[str]:
    node = puzzle.game.end()
    board = node.board()
    king = board.king(not puzzle.pov)
    assert king is not None
    assert isinstance(node, ChildNode)
    if square_file(king) in [0, 7] or chess.square_rank(king) in [0, 7]:
        return None
    queen_square = node.move.to_square
    if (util.moved_piece_type(node) != QUEEN or
        square_file(queen_square) == square_file(king) or
        chess.square_rank(queen_square) == chess.square_rank(king) or
        chess.square_distance(queen_square, king) > 1):
        return None
    for square in [s for s in SquareSet(chess.BB_ALL) if chess.square_distance(s, king) == 1]:
        if square == queen_square:
            continue
        attackers = list(board.attackers(puzzle.pov, square))
        if attackers == [queen_square] and board.piece_at(square) or attackers:
            if board.piece_at(square):
                return None
        elif attackers:
            return None
    return "dovetailMate"


def piece_endgame(puzzle: Puzzle, piece_type: chess.PieceType) -> bool:
    for board in [puzzle.mainline[i].board() for i in [0, 1]]:
        if not board.pieces(piece_type, chess.WHITE) and not board.pieces(piece_type, chess.BLACK):
            return False
        for piece in board.piece_map().values():
            if not piece.piece_type in [KING, PAWN, piece_type]:
                return False
    return True


def queen_rook_endgame(puzzle: Puzzle) -> bool:
    def test(board: chess.Board) -> bool:
        pieces = board.piece_map().values()
        return (
            len([p for p in pieces if p.piece_type == QUEEN]) == 1 and
            any(p.piece_type == ROOK for p in pieces) and
            all(p.piece_type in [QUEEN, ROOK, PAWN, KING] for p in pieces)
        )

    return all(test(puzzle.mainline[i].board()) for i in [0, 1])


def smothered_mate(puzzle: Puzzle) -> Optional[str]:
    board = puzzle.game.end().board()
    king_square = board.king(not puzzle.pov)
    assert king_square is not None
    for checker_square in board.checkers():
        piece = board.piece_at(checker_square)
        assert piece
        if piece.piece_type == KNIGHT:
            for escape_square in [s for s in chess.SQUARES if chess.square_distance(s, king_square) == 1]:
                blocker = board.piece_at(escape_square)
                if not blocker or blocker.color == puzzle.pov:
                    return None
            return "smotheredMate"
    return None


def mate_in(puzzle: Puzzle) -> Optional[TagKind]:
    if not puzzle.game.end().board().is_checkmate():
        return None
    moves_to_mate = len(puzzle.mainline) // 2
    if moves_to_mate == 1:
        return "mateIn1"
    elif moves_to_mate == 2:
        return "mateIn2"
    elif moves_to_mate == 3:
        return "mateIn3"
    elif moves_to_mate == 4:
        return "mateIn4"
    return "mateIn5"


def attacking_f2_f7(node: ChildNode) -> str:
    square = node.move.to_square
    if node.parent.board().piece_at(node.move.to_square) and square in [chess.F2, chess.F7]:
        king = node.board().piece_at(chess.E8 if square == chess.F7 else chess.E1)
        if king is not None and king.piece_type == KING and king.color != pov_from_node(node):
            return "attackingF2F7"
    return None
