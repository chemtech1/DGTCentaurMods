# This file is part of the DGTCentaur Mods open source software
# ( https://github.com/Alistair-Crompton/DGTCentaurMods )
#
# DGTCentaur Mods is free software: you can redistribute
# it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
#
# DGTCentaur Mods is distributed in the hope that it will
# be useful, but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this file.  If not, see
#
# https://github.com/Alistair-Crompton/DGTCentaurMods/blob/master/LICENSE.md
#
# This and any other notices must remain intact and unaltered in any
# distribution, modification, variant, or derivative of this software.

import chess
import random
import os
import csv
from typing import Optional, Dict, List
import threading
import time
from pathlib import Path
from collections import defaultdict

from DGTCentaurMods.classes.Plugin import Plugin, Centaur
from DGTCentaurMods.classes import Log
from DGTCentaurMods.classes.GameFactory import Engine
from DGTCentaurMods.classes import CentaurScreen as SCREEN
from DGTCentaurMods.classes.CentaurConfig import CentaurConfig
from DGTCentaurMods.consts import Enums, fonts, consts
from PIL import ImageDraw

# Row positions of the three menu entries (for partial update)
_MENU_ROW_PREV    = 3
_MENU_ROW_CURRENT = 4
_MENU_ROW_NEXT    = 5
# Y-coordinates for clear_area (HEADER_HEIGHT = 20px)
_MENU_AREA_Y1 = _MENU_ROW_PREV    * 20      # 60
_MENU_AREA_Y2 = (_MENU_ROW_NEXT + 1) * 20   # 120

class PuzzleBot(Plugin):
    """
    Lichess Puzzle Plugin for the DGT Centaur.
    The player selects a category (Mate in 2/3/4) and rating.
    A random puzzle is loaded and set up on the board.
    The framework checks whether all pieces are correctly placed (blinking LEDs).
    The engine plays the first move of the puzzle.
    The player must then play all remaining puzzle moves correctly.
    """

    _menu_state: str = 'splash'
    _selected_category: Optional[str] = None
    _selected_type: Optional[str] = None
    _selected_rating: Optional[str] = None
    _current_index: int = 0
    puzzle_structure: Dict = {}
    _current_puzzle: Optional[Dict] = None
    _current_move_index: int = 0
    _human_color: Optional[chess.Color] = None
    _puzzle_state: Optional[str] = None  # None=menu, 'setup'=arranging board, 'playing'=puzzle running
    _board_setup_thread: Optional[threading.Thread] = None
    _menu_static_drawn: bool = False  # flag: static frame already drawn?

    def __init__(self, id: str):
        super().__init__(id)
        self.puzzle_structure = self.scan_puzzle_structure()
        Log.info("PuzzleBot initialized")

    def splash_screen(self) -> bool:
        """Displays the splash screen when the plugin starts."""
        screen = SCREEN.get()
        Centaur.clear_screen()

        # Decorative separator line at the top
        screen.draw_rectangle(10, 22, 117, 23, fill=0, outline=0)

        # Title: PUZZLE BOT
        Centaur.print("PUZZLE", row=2, font=fonts.DIGITAL_FONT)
        Centaur.print("BOT", row=3, font=fonts.DIGITAL_FONT)

        # Decorative separator line below the title
        screen.draw_rectangle(10, 82, 117, 83, fill=0, outline=0)

        # Subtitle
        Centaur.print("Lichess Puzzles", row=5)
        Centaur.print("Mate / Opening", row=6, font=fonts.SMALL_MAIN_FONT)

        # Button labels
        Centaur.print_button_label(Enums.Btn.PLAY, 0, text="START")
        Centaur.print_button_label(Enums.Btn.BACK, 0, text="BACK")

        Log.debug("Splash screen displayed")
        return True

    def scan_puzzle_structure(self) -> Dict[str, Dict[str, List[str]]]:
        """
        Scans the data directory for puzzle categories, types, and ratings.
        Rating is stored as the raw string after the last '_' in the filename
        (e.g. "ELO 1000" from "mate in 2_ELO 1000.csv").
        """
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(os.path.dirname(plugin_dir), "data")
        structure = defaultdict(lambda: defaultdict(list))

        for category_folder in sorted(Path(data_dir).iterdir()):
            if not category_folder.is_dir():
                continue
            category = category_folder.name

            for file in sorted(category_folder.glob("*.csv")):
                name = file.stem
                # Schema: "hookMate_ELO_1000" → type="hookMate", rating="ELO_1000"
                parts = name.rsplit('_', 2)
                if len(parts) == 3:
                    puzzle_type = parts[0]
                    rating = f"{parts[1]}_{parts[2]}"  # e.g. "ELO_1000"
                elif len(parts) == 2:
                    puzzle_type = parts[0]
                    rating = parts[1]
                else:
                    puzzle_type = name
                    rating = ""

                if rating:
                    structure[category][puzzle_type].append(rating)

        # Sort ratings alphabetically (works for "ELO 1000" … "ELO 2500")
        for cat in structure.values():
            for typ in cat.values():
                typ.sort()

        return dict(structure)

    def _get_categories(self) -> List[str]:
        """Returns sorted list of categories."""
        return sorted(self.puzzle_structure.keys())

    def _get_types(self, category: str) -> List[str]:
        """Returns sorted list of types for a category."""
        return sorted(self.puzzle_structure.get(category, {}).keys())

    def _get_ratings(self, category: str, typ: str) -> List[str]:
        """Returns sorted list of rating strings for a type in a category."""
        return self.puzzle_structure.get(category, {}).get(typ, [])

    def _get_menu_display_items(self) -> tuple:
        """Returns (prev, current, next) items for rolling menu display."""
        items = []
        if self._menu_state == 'category':
            items = self._get_categories()
        elif self._menu_state == 'type':
            items = self._get_types(self._selected_category)
        elif self._menu_state == 'rating':
            items = self._get_ratings(self._selected_category, self._selected_type)

        if not items:
            return "", "", ""

        len_items = len(items)
        prev = items[(self._current_index - 1) % len_items] if len_items > 1 else ""
        current = items[self._current_index % len_items]
        next_ = items[(self._current_index + 1) % len_items] if len_items > 1 else ""
        return prev, current, next_

    def _get_total_puzzles(self) -> int:
        """Returns total number of puzzles in current menu state."""
        if self._menu_state == 'category':
            return sum(len(types) for types in self.puzzle_structure.values() for typ in types.values())
        elif self._menu_state == 'type':
            return sum(len(ratings) for ratings in self.puzzle_structure.get(self._selected_category, {}).values())
        elif self._menu_state == 'rating':
            return len(self._get_ratings(self._selected_category, self._selected_type))
        return 0

    def load_random_puzzle(self, category: str, typ: str, rating: str) -> Optional[Dict]:
        """Loads a random puzzle from the CSV file for the given category, type, and rating string."""
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(os.path.dirname(plugin_dir), "data")
        filepath = os.path.join(data_dir, category, f"{typ}_{rating}.csv")
        Log.info(f"Loading puzzle from: {filepath}")

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                puzzles = list(reader)
                if not puzzles:
                    Log.info(f"No puzzles found in file: {filepath}")
                    return None
                puzzle = random.choice(puzzles)
                # Support both Lichess CamelCase headers and legacy lowercase headers
                puzzle_id = puzzle.get('PuzzleId') or puzzle.get('id') or '?'
                fen       = puzzle.get('FEN')      or puzzle.get('fen') or ''
                moves_str = puzzle.get('Moves')    or puzzle.get('moves') or ''
                rating_v  = puzzle.get('Rating')   or puzzle.get('rating') or '0'
                themes    = puzzle.get('Themes')   or puzzle.get('themes') or ''
                if not fen or not moves_str:
                    Log.info(f"Puzzle {puzzle_id} has no FEN or moves – skipping")
                    return None
                Log.info(f"Loaded puzzle {puzzle_id} with rating {rating_v}")
                return {
                    'id':     puzzle_id,
                    'fen':    fen,
                    'moves':  moves_str.split(),
                    'rating': int(rating_v),
                    'themes': themes,
                }
        except Exception as e:
            Log.exception(self.load_random_puzzle, f"Error loading puzzle from {filepath}: {e}")
            return None

    def _draw_menu_frame(self):
        """
        Draws the selection frame around the current menu entry (row 4).
        Called once per state change; persists across UP/DOWN navigation.
        """
        screen = SCREEN.get()
        # Row 4: Y = 4 * 20 = 80, height = 20px → Y 80..99
        y_top    = _MENU_ROW_CURRENT * 20       # 80
        y_bottom = y_top + 19                   # 99
        canvas = ImageDraw.Draw(screen._buffer)
        canvas.rounded_rectangle(
            [(0, y_top), (127, y_bottom)],
            radius=8,
            fill=None,
            outline="black",
            width=1
        )

    def _draw_menu_static(self):
        """
        Draws the static part of the menu (title, buttons).
        Called only once per menu state change.
        """
        Centaur.clear_screen()

        # Row 1: title
        Centaur.print("Menu", row=1)

        # Rows 3-5: placeholders – filled by _draw_menu_items()

        # Row 8: scroll hint
        Centaur.print("UP/DOWN scroll", row=8)

        # Row 9: select action
        Centaur.print("PLAY = Select", row=9)

        # Row 10: back action
        Centaur.print("BACK = Back", row=10)

        # NOTE: _draw_menu_frame() is NOT called here – write_text() would
        # overwrite the buffer and erase the frame. The frame is drawn in
        # _draw_menu_items() AFTER all write_text() calls.

        self._menu_static_drawn = True

    def _draw_menu_items(self):
        """
        Redraws only the three rolling menu rows (prev / current / next).
        The frame is drawn AFTER all write_text() calls so it is not overwritten.
        """
        screen = SCREEN.get()

        prev, current, next_ = self._get_menu_display_items()

        # Prev row (Y 60–79): clear + redraw text
        screen.draw_rectangle(0, _MENU_AREA_Y1, 128, _MENU_ROW_CURRENT * 20 - 1, fill=255, outline=255)
        screen.write_text(_MENU_ROW_PREV, prev, font=fonts.SMALL_MAIN_FONT)

        # Current row: clear + redraw text
        y_frame_top = _MENU_ROW_CURRENT * 20   # 80
        screen.draw_rectangle(0, y_frame_top, 128, _MENU_ROW_NEXT * 20 - 1, fill=255, outline=255)
        # MEDIUM_MAIN_FONT (13px) – slightly larger than prev/next (11px)
        screen.write_text(_MENU_ROW_CURRENT, current, font=fonts.MEDIUM_MAIN_FONT)

        # Next row (Y 100–119): clear + redraw text
        screen.draw_rectangle(0, _MENU_ROW_NEXT * 20, 128, _MENU_AREA_Y2, fill=255, outline=255)
        screen.write_text(_MENU_ROW_NEXT, next_, font=fonts.SMALL_MAIN_FONT)

        # Draw frame LAST so write_text() cannot overwrite it
        self._draw_menu_frame()

    def _update_menu_display(self, full_rebuild: bool = False):
        """
        Updates the menu display.
        full_rebuild=True → rebuild the entire screen (on state change).
        full_rebuild=False → redraw only the three menu rows (on UP/DOWN).
        """
        if self._menu_state == 'splash':
            self.splash_screen()
            self._menu_static_drawn = False
            return

        if full_rebuild or not self._menu_static_drawn:
            self._draw_menu_static()

        self._draw_menu_items()

        Log.debug(f"Menu display updated: state={self._menu_state}, index={self._current_index}")

    def _wait_for_board_setup(self):
        """
        Thread function: waits until the board is correctly arranged.
        Once the board matches the puzzle FEN, the engine's first move is played.
        """
        timeout = time.time() + 300  # 5-minute timeout
        
        while self._puzzle_state == 'setup' and time.time() < timeout:
            try:
                # Check whether the board is correctly set up
                if not self.game_engine._invalid_board_state:
                    # Board is correct – play the first move
                    Log.info("Board setup complete! Playing first move...")
                    self._puzzle_state = 'playing'
                    
                    if self._current_puzzle and self._current_puzzle['moves']:
                        first_move = self._current_puzzle['moves'][0]

                        # Push two null sentinels NOW (after setup, before first move).
                        # Two nulls cancel each other out → turn stays the same.
                        # Prevents an empty move_stack crash on takeback of the first engine move:
                        # After takeback: stack=[null1,null2] → peek()=null2 → no crash.
                        self.chessboard.push(chess.Move.null())
                        self.chessboard.push(chess.Move.null())
                        Log.info("Double null sentinel pushed before first move")

                        Log.info(f"Playing first move: {first_move}")
                        Centaur.play_computer_move(first_move)
                    
                    # Update web UI after board setup (directly, without last_uci_move)
                    self._send_web_update(None)
                    break
                
                time.sleep(0.5)
            except Exception as e:
                Log.exception(self._wait_for_board_setup, f"Error in board setup thread: {e}")
                break

    def key_callback(self, key: Enums.Btn):
        """Handles key inputs for the rolling menu system."""

        # Solved menu navigation
        if self._puzzle_state == 'solved':
            if key == Enums.Btn.UP:
                self._solved_menu_index = (self._solved_menu_index - 1) % len(self._SOLVED_MENU_ITEMS)
                self._update_solved_menu()
                return True
            elif key == Enums.Btn.DOWN:
                self._solved_menu_index = (self._solved_menu_index + 1) % len(self._SOLVED_MENU_ITEMS)
                self._update_solved_menu()
                return True
            elif key == Enums.Btn.PLAY:
                choice = self._SOLVED_MENU_ITEMS[self._solved_menu_index]
                Log.info(f"Solved menu choice: {choice}")
                if choice == "Repeat":
                    # Restart the same puzzle
                    self._restart_current_puzzle()
                elif choice == "Another Puzzle":
                    # Load a new random puzzle from the same category/type/rating
                    self._load_next_puzzle()
                elif choice == "New Selection":
                    # Return to the puzzle selection menu (without stopping the plugin)
                    self._puzzle_state = None
                    self._current_puzzle = None
                    self._current_move_index = 0
                    self._menu_state = 'category'
                    self._current_index = 0
                    self._menu_static_drawn = False
                    self._update_menu_display(full_rebuild=True)
                elif choice == "Exit":
                    self.stop()
                return True
            elif key == Enums.Btn.BACK:
                self.stop()
                return True
            return False

        # If puzzle is playing: only allow BACK to exit
        if self._puzzle_state == 'playing':
            if key == Enums.Btn.BACK:
                Log.info("Player exited puzzle")
                self.stop()
                return True
            elif key == Enums.Btn.HELP:
                # Show hint for expected move – only if hints are enabled in the web menu
                if CentaurConfig.get_hint_settings(consts.HINT_ENABLED):
                    if self._current_move_index < len(self._current_puzzle['moves']):
                        if self.chessboard.turn == self._human_color:
                            expected_move = self._current_puzzle['moves'][self._current_move_index]
                            # Flash only the source square (the piece), not the destination
                            Centaur.flash(expected_move[0:2])
                            Log.info(f"Hint shown (source only): {expected_move[0:2]}")
                else:
                    Log.info("Hint disabled in web menu")
                return True
            return False

        # If board is being set up: only allow BACK to cancel
        if self._puzzle_state == 'setup':
            if key == Enums.Btn.BACK:
                Log.info("Player cancelled puzzle setup")
                self._puzzle_state = None
                self._menu_state = 'rating'
                self._menu_static_drawn = False
                self._update_menu_display(full_rebuild=True)
                return True
            return False

        # Menu navigation
        if self._menu_state == 'splash':
            if key == Enums.Btn.PLAY:
                self._menu_state = 'category'
                self._current_index = 0
                self._menu_static_drawn = False
                self._update_menu_display(full_rebuild=True)
                return True
            elif key == Enums.Btn.BACK:
                self.stop()
                return True
            return False

        elif self._menu_state in ['category', 'type', 'rating']:
            items = []
            if self._menu_state == 'category':
                items = self._get_categories()
            elif self._menu_state == 'type':
                items = self._get_types(self._selected_category)
            elif self._menu_state == 'rating':
                items = self._get_ratings(self._selected_category, self._selected_type)

            if key == Enums.Btn.UP:
                self._current_index = (self._current_index - 1) % len(items)
                # Redraw only menu rows – no full-screen refresh
                self._update_menu_display(full_rebuild=False)
                return True
            elif key == Enums.Btn.DOWN:
                self._current_index = (self._current_index + 1) % len(items)
                # Redraw only menu rows – no full-screen refresh
                self._update_menu_display(full_rebuild=False)
                return True
            elif key == Enums.Btn.PLAY:
                selected = items[self._current_index]
                if self._menu_state == 'category':
                    self._selected_category = selected
                    self._menu_state = 'type'
                    self._current_index = 0
                    self._menu_static_drawn = False
                elif self._menu_state == 'type':
                    self._selected_type = selected
                    self._menu_state = 'rating'
                    self._current_index = 0
                    self._menu_static_drawn = False
                elif self._menu_state == 'rating':
                    # Load puzzle – remember the bucket rating string for "Another Puzzle"
                    self._selected_rating = selected   # e.g. "ELO 1000"
                    puzzle = self.load_random_puzzle(self._selected_category, self._selected_type, selected)
                    if puzzle is None:
                        Centaur.header("Failed to load puzzle")
                        return False

                    self._current_puzzle = puzzle
                    self._current_move_index = 0
                    self._human_color = not chess.Board(puzzle['fen']).turn

                    white = "You" if self._human_color == chess.WHITE else "Lichess Puzzle"
                    black = "Lichess Puzzle" if self._human_color == chess.WHITE else "You"

                    Log.info(f"Puzzle loaded: {puzzle['id']}")
                    Log.info(f"Puzzle FEN: {puzzle['fen']}")
                    Log.info(f"Puzzle moves: {puzzle['moves']}")
                    Log.info(f"Human plays: {self._human_color}")

                    # Start the game
                    flags = Enums.BoardOption.CAN_UNDO_MOVES | Enums.BoardOption.RESUME_DISABLED
                    Centaur.start_game(white=white, black=black, event="Lichess Puzzle Challenge", flags=flags)

                    # Set the puzzle FEN
                    self.chessboard.set_fen(puzzle['fen'])

                    # Initialize the game engine manually
                    try:
                        self.game_engine._need_starting_position_check = False
                        self.game_engine._Engine__initialize()
                        self.game_engine._invalid_board_state = True
                        self.game_engine._initialized = True

                        # Update board state (shows wrong fields with LEDs)
                        self.game_engine._update_board_state(False)

                        # Do NOT call update_web_ui() here – the move_stack is still empty,
                        # but ply() > 0 due to the FEN fullmove number → IndexError in peek().
                        # The web UI is updated in _wait_for_board_setup() once the board
                        # is correctly arranged.

                        Log.info("Game engine initialized for puzzle")
                    except Exception as e:
                        Log.exception(self.key_callback, f"Error initializing game engine: {e}")
                        Centaur.header("Engine error")
                        self.stop()
                        return False

                    # Patch update_web_ui so 'pgn' is never sent to the web client.
                    # history.js initFromPGN() always resets to the standard starting
                    # position, which would overwrite the puzzle FEN after every move.
                    self._patch_update_web_ui()

                    # Show the board on the display
                    SCREEN.get().draw_fen(puzzle['fen'], startrow=1.6)

                    # Start the board setup thread
                    self._puzzle_state = 'setup'
                    self._board_setup_thread = threading.Thread(target=self._wait_for_board_setup, daemon=True)
                    self._board_setup_thread.start()

                    Log.info("Puzzle setup started - waiting for board to be arranged")
                    return True

                # State transition (category→type or type→rating): full rebuild
                self._update_menu_display(full_rebuild=True)
                return True
            elif key == Enums.Btn.BACK:
                if self._menu_state == 'category':
                    self._menu_state = 'splash'
                    self._menu_static_drawn = False
                    self.splash_screen()
                elif self._menu_state == 'type':
                    self._menu_state = 'category'
                    self._current_index = 0
                    self._menu_static_drawn = False
                    self._update_menu_display(full_rebuild=True)
                elif self._menu_state == 'rating':
                    self._menu_state = 'type'
                    self._current_index = 0
                    self._menu_static_drawn = False
                    self._update_menu_display(full_rebuild=True)
                return True

        return False

    def event_callback(self, event: Enums.Event, outcome: Optional[chess.Outcome]):
        """Handles game engine events."""
        
        # Player wants to quit
        if event == Enums.Event.QUIT:
            Log.info("Plugin stopped by user")
            self.stop()
            return

        # Game ended (checkmate, stalemate, etc.)
        if event == Enums.Event.TERMINATION:
            if outcome and outcome.winner == self._human_color:
                Centaur.sound(Enums.Sound.VICTORY)
            else:
                Centaur.sound(Enums.Sound.GAME_LOST)
            return

        # Player or engine must make a move
        if event == Enums.Event.PLAY:
            if self._current_puzzle is None or self._puzzle_state != 'playing':
                return
            
            turn = self.chessboard.turn
            current_player = "You" if turn == self._human_color else "Lichess Puzzle"
            Centaur.header(f"{current_player} {'W' if turn == chess.WHITE else 'B'}")
            
            # Player's turn
            if turn == self._human_color:
                Log.info(f"Player turn. Expected move: {self._current_puzzle['moves'][self._current_move_index] if self._current_move_index < len(self._current_puzzle['moves']) else 'PUZZLE COMPLETE'}")
            
            # Engine's turn
            else:
                if self._current_move_index < len(self._current_puzzle['moves']):
                    next_move = self._current_puzzle['moves'][self._current_move_index]
                    Log.info(f"Engine turn. Playing move: {next_move}")
                    Centaur.play_computer_move(next_move)

    def move_callback(self, uci_move: str, san_move: str, color: chess.Color, field_index: chess.Square) -> bool:
        """Processes moves and checks whether they are correct."""
        
        if self._current_puzzle is None or self._puzzle_state != 'playing':
            return True

        Log.info(f"Move callback: {uci_move} by {'Player' if color == self._human_color else 'Engine'}")

        # Player move – check if it is correct
        if color == self._human_color:
            if self._current_move_index >= len(self._current_puzzle['moves']):
                # Puzzle already solved
                Log.info("Puzzle already solved!")
                return True
            
            expected_move = self._current_puzzle['moves'][self._current_move_index]
            
            if uci_move != expected_move:
                # Wrong move – framework automatically pops and rejects it
                Log.info(f"Wrong move! Expected: {expected_move}, got: {uci_move}")
                Centaur.sound(Enums.Sound.WRONG_MOVE)
                Centaur.header("Wrong move!")
                return False
            
            # Correct move
            Log.info(f"Correct move! {uci_move}")
            self._current_move_index += 1

            # Update web UI after player move (directly, without last_uci_move)
            self._send_web_update(uci_move)
            
            # Check whether the puzzle is solved
            if self._current_move_index >= len(self._current_puzzle['moves']):
                Log.info("Puzzle solved!")
                Centaur.sound(Enums.Sound.VICTORY)
                Centaur.header("Puzzle solved!")
                self._puzzle_state = 'solved'
                self._show_solved_menu()
            
            return True
        
        # Engine move – accept it and advance the index
        else:
            Log.info(f"Engine move accepted: {uci_move}")
            self._current_move_index += 1

            # Update web UI after engine move (directly, without last_uci_move)
            self._send_web_update(uci_move)

            return True

    def undo_callback(self, uci_move: str, san_move: str, field_index: chess.Square):
        """
        Handles move takebacks.
        Decrements the puzzle move index so the engine replays the correct move
        after the undo.

        The two null sentinels at the bottom of the stack cannot be physically
        undone (no null-move gesture exists on the board), so no null handling
        is needed.
        """
        if self._current_puzzle is None or self._puzzle_state != 'playing':
            return

        if uci_move == "0000":
            # Null sentinel was undone (should not happen) – ignore
            Log.info("Null sentinel undo ignored")
            return

        self._current_move_index = max(0, self._current_move_index - 1)
        Log.info(f"Takeback: {uci_move}, index → {self._current_move_index}")

    def _patch_update_web_ui(self):
        """
        Monkey-patches game_engine.update_web_ui so that 'pgn' is never sent
        to the web client.

        Background: history.js initFromPGN() always rebuilds the FEN history
        starting from the standard starting position (START_FEN), ignoring any
        [FEN ...] header in the PGN.  Sending a pgn key therefore resets the
        board to the standard starting position after every move.

        By omitting 'pgn' the JS pgn handler is never called and the board
        stays at the position set via the 'fen' key.
        """
        engine = self.game_engine
        def _patched(args={}):
            if not engine._started:
                return
            try:
                uci = engine.last_uci_move
            except Exception:
                uci = None
            wk = engine._chessboard.king(chess.WHITE)
            bk = engine._chessboard.king(chess.BLACK)
            message = {
                "fen": engine._chessboard.fen(),
                "uci_move": uci,
                "checkers": [chess.square_name(sq) for sq in engine._chessboard.checkers()],
                "kings": [
                    chess.square_name(wk) if wk is not None else "e1",
                    chess.square_name(bk) if bk is not None else "e8",
                ],
                **args
            }
            # 'pgn' deliberately omitted – see docstring above
            engine.send_message_to_web_ui(message)
        engine.update_web_ui = _patched

        # Suppress DAL.terminate_game crash on checkmate at puzzle end.
        # Our manual engine init (FEN override) does not create a matching
        # DB game row, so the lookup returns None → AttributeError.
        # Puzzle plugins do not need DAL game tracking.
        engine._dal.terminate_game = lambda result: None

    def _send_web_update(self, uci_move: Optional[str] = None):
        """
        Sends the current board state to the web interface.
        Uses send_message_to_web_ui directly to avoid calling last_uci_move
        (which crashes with a peek() IndexError when null sentinels are on top
        of the move stack).
        """
        try:
            board = self.chessboard
            wk = board.king(chess.WHITE)
            bk = board.king(chess.BLACK)
            self.game_engine.send_message_to_web_ui({
                "fen": board.fen(),
                "uci_move": uci_move,
                "checkers": [chess.square_name(sq) for sq in board.checkers()],
                "kings": [
                    chess.square_name(wk) if wk is not None else "e1",
                    chess.square_name(bk) if bk is not None else "e8",
                ],
            })
        except Exception as e:
            Log.exception(self._send_web_update, e)

    # Solved menu: 3 items (Repeat / Another Puzzle / Exit)
    # Displayed below the board (rows 9-11, Y 180-239)
    # Row 9  = index 0 = "Repeat"
    # Row 10 = index 1 = "Another Puzzle"  ← default
    # Row 11 = index 2 = "Exit"
    _SOLVED_MENU_ITEMS = ["Repeat", "Another Puzzle", "Exit"]
    _SOLVED_MENU_BASE_ROW = 9   # first menu row
    _solved_menu_index: int = 1

    def _show_solved_menu(self):
        """
        Displays the post-puzzle menu BELOW the board.
        The board (rows 2-8) stays visible.
        Options: Repeat | Another Puzzle | Exit
        """
        screen = SCREEN.get()

        # Separator line above the menu area
        screen.draw_rectangle(0, 178, 128, 179, fill=0, outline=0)

        # Menu options (rows 9-11)
        self._solved_menu_index = 1  # default: "Another Puzzle"
        self._draw_solved_menu_items()

        Log.info("Solved menu displayed")

    def _draw_solved_menu_items(self):
        """Draws all solved-menu rows and the selection frame."""
        screen = SCREEN.get()
        base = self._SOLVED_MENU_BASE_ROW
        for i, item in enumerate(self._SOLVED_MENU_ITEMS):
            row = base + i
            y_top    = row * 20
            y_bottom = y_top + 19
            screen.draw_rectangle(0, y_top, 128, y_bottom, fill=255, outline=255)
            f = fonts.MEDIUM_MAIN_FONT if i == self._solved_menu_index else fonts.SMALL_MAIN_FONT
            screen.write_text(row, item, font=f)
        self._draw_solved_menu_frame()

    def _draw_solved_menu_frame(self):
        """Draws the selection frame around the currently highlighted solved-menu entry."""
        screen = SCREEN.get()
        row     = self._SOLVED_MENU_BASE_ROW + self._solved_menu_index
        y_top    = row * 20
        y_bottom = y_top + 19
        canvas = ImageDraw.Draw(screen._buffer)
        canvas.rounded_rectangle(
            [(0, y_top), (127, y_bottom)],
            radius=8,
            fill=None,
            outline="black",
            width=1
        )

    def _update_solved_menu(self):
        """Redraws the solved-menu rows (3 option rows + frame)."""
        self._draw_solved_menu_items()

    def _restart_current_puzzle(self):
        """Restarts the current puzzle (same FEN, same moves)."""
        if self._current_puzzle is None:
            return
        Log.info(f"Restarting puzzle {self._current_puzzle['id']}")
        puzzle = self._current_puzzle
        self._current_move_index = 0

        white = "You" if self._human_color == chess.WHITE else "Lichess Puzzle"
        black = "Lichess Puzzle" if self._human_color == chess.WHITE else "You"

        flags = Enums.BoardOption.CAN_UNDO_MOVES | Enums.BoardOption.RESUME_DISABLED
        Centaur.start_game(white=white, black=black, event="Lichess Puzzle Challenge", flags=flags)
        self.chessboard.set_fen(puzzle['fen'])

        try:
            self.game_engine._need_starting_position_check = False
            self.game_engine._Engine__initialize()
            self.game_engine._invalid_board_state = True
            self.game_engine._initialized = True
            self.game_engine._update_board_state(False)
        except Exception as e:
            Log.exception(self._restart_current_puzzle, e)
            return

        # Patch update_web_ui so 'pgn' is never sent to the web client
        self._patch_update_web_ui()

        SCREEN.get().draw_fen(puzzle['fen'], startrow=1.6)
        self._puzzle_state = 'setup'
        self._board_setup_thread = threading.Thread(target=self._wait_for_board_setup, daemon=True)
        self._board_setup_thread.start()
        Log.info("Puzzle restart: waiting for board setup")

    def _load_next_puzzle(self):
        """Loads a new random puzzle from the same category/type/rating."""
        if self._selected_category is None or self._selected_type is None:
            self.stop()
            return
        # Use the bucket rating chosen in the menu, NOT the individual puzzle rating
        rating = self._selected_rating if self._selected_rating is not None else 1000
        puzzle = self.load_random_puzzle(self._selected_category, self._selected_type, rating)
        if puzzle is None:
            Centaur.header("No puzzle found")
            return

        self._current_puzzle = puzzle
        self._current_move_index = 0
        self._human_color = not chess.Board(puzzle['fen']).turn

        white = "You" if self._human_color == chess.WHITE else "Lichess Puzzle"
        black = "Lichess Puzzle" if self._human_color == chess.WHITE else "You"

        Log.info(f"Next puzzle: {puzzle['id']}")
        flags = Enums.BoardOption.CAN_UNDO_MOVES | Enums.BoardOption.RESUME_DISABLED
        Centaur.start_game(white=white, black=black, event="Lichess Puzzle Challenge", flags=flags)
        self.chessboard.set_fen(puzzle['fen'])

        try:
            self.game_engine._need_starting_position_check = False
            self.game_engine._Engine__initialize()
            self.game_engine._invalid_board_state = True
            self.game_engine._initialized = True
            self.game_engine._update_board_state(False)
        except Exception as e:
            Log.exception(self._load_next_puzzle, e)
            return

        # Patch update_web_ui so 'pgn' is never sent to the web client
        self._patch_update_web_ui()

        SCREEN.get().draw_fen(puzzle['fen'], startrow=1.6)
        self._puzzle_state = 'setup'
        self._board_setup_thread = threading.Thread(target=self._wait_for_board_setup, daemon=True)
        self._board_setup_thread.start()
        Log.info("Next puzzle: waiting for board setup")

    def on_socket_request(self, data: dict) -> bool:
        """Handles socket requests from the web interface."""
        return False

    def on_stop_callback(self):
        """Called when the plugin is stopped."""
        self._menu_state = 'splash'
        self._selected_category = None
        self._selected_type = None
        self._selected_rating = None
        self._current_index = 0
        self._puzzle_state = None
        self._current_puzzle = None
        self._menu_static_drawn = False
        Log.info("PuzzleBot stopped")
