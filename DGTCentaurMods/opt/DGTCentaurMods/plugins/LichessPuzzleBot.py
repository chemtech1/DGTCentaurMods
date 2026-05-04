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

from DGTCentaurMods.classes.Plugin import Plugin, Centaur
from DGTCentaurMods.classes import Log
from DGTCentaurMods.classes.GameFactory import Engine
from DGTCentaurMods.classes import CentaurScreen as SCREEN
from DGTCentaurMods.consts import Enums, fonts

class LichessPuzzleBot(Plugin):
    """
    Lichess Puzzle Plugin for the DGT Centaur.
    Spieler wählt Kategorie (Matt in 2/3/4) und Rating aus.
    Ein zufälliges Puzzle wird geladen und auf dem Brett aufgestellt.
    Das Framework prüft, ob alle Figuren richtig stehen (blinkende LEDs).
    Die Engine spielt den ersten Zug des Puzzles.
    Der Spieler muss dann alle Züge des Puzzles korrekt spielen.
    """

    _puzzle_categories: Dict[str, str] = {
        'mate2': 'mate2',
        'mate3': 'mate3',
        'mate4': 'mate4',
    }

    _rating_levels: List[int] = [1000, 1300, 1600, 1900, 2200, 2500]

    _selected_category: Optional[str] = None
    _selected_rating: Optional[int] = None
    _current_puzzle: Optional[Dict] = None
    _current_move_index: int = 0
    _current_mate_type: str = 'mate2'
    _current_rating_index: int = 0
    _menu_state: Optional[str] = None
    _human_color: Optional[chess.Color] = None
    _puzzle_state: Optional[str] = None  # None=Menü, 'setup'=Brett aufstellen, 'playing'=Puzzle läuft
    _board_setup_thread: Optional[threading.Thread] = None

    def __init__(self, id: str):
        super().__init__(id)
        Log.info("LichessPuzzleBot initialized")

    def splash_screen(self) -> bool:
        """Splash-Screen beim Start des Plugins"""
        Centaur.clear_screen()
        Centaur.print("LICHESS", row=2, font=fonts.DIGITAL_FONT)
        Centaur.print("PUZZLES", row=4, font=fonts.DIGITAL_FONT)

        Centaur.print_button_label(Enums.Btn.PLAY, 0, text="START")
        Centaur.print_button_label(Enums.Btn.BACK, 0, text="BACK")

        Log.debug("Splash screen displayed")
        return True

    def load_random_puzzle(self) -> Optional[Dict]:
        """Lädt ein zufälliges Puzzle aus der CSV-Datei"""
        # Absoluter Pfad zur data-Datei
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(os.path.dirname(plugin_dir), "data")
        
        filename = f"{self._puzzle_categories[self._current_mate_type]}_{self._rating_levels[self._current_rating_index]}.csv"
        filepath = os.path.join(data_dir, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                puzzles = list(reader)
                if not puzzles:
                    Log.info("No puzzles found in file")
                    return None
                puzzle = random.choice(puzzles)
                Log.info(f"Loaded puzzle {puzzle['id']} with rating {puzzle['rating']}")
                return {
                    'id': puzzle['id'],
                    'fen': puzzle['fen'],
                    'moves': puzzle['moves'].split(),
                    'rating': int(puzzle['rating']),
                    'themes': puzzle['themes']
                }
        except Exception as e:
            Log.exception(self.load_random_puzzle, f"Error loading puzzle: {e}")
            return None

    def _update_menu_display(self):
        """Aktualisiert die Menü-Anzeige auf dem Display"""
        Centaur.clear_screen()
        
        if self._menu_state == 'mate':
            mate_num = self._current_mate_type[-1]  # '2' from 'mate2'
            Centaur.print(f"Mate in {mate_num}", row=2, font=fonts.DIGITAL_FONT)
            Centaur.print("UP/DOWN: Change mate", row=8)
            Centaur.print("PLAY: Select", row=9)
            Centaur.print("BACK: Back", row=10)
        elif self._menu_state == 'rating':
            rating = self._rating_levels[self._current_rating_index]
            Centaur.print(f"Rating {rating}", row=2, font=fonts.DIGITAL_FONT)
            Centaur.print("UP/DOWN: Change rating", row=8)
            Centaur.print("PLAY: Start puzzle", row=9)
            Centaur.print("BACK: Back", row=10)
        
        Log.debug(f"Menu display updated: state={self._menu_state}, mate={self._current_mate_type}, rating_idx={self._current_rating_index}")

    def _wait_for_board_setup(self):
        """
        Thread-Funktion: Wartet darauf, dass das Brett korrekt aufgestellt ist.
        Sobald das Brett dem Puzzle-FEN entspricht, wird der erste Zug gespielt.
        """
        timeout = time.time() + 300  # 5 Minuten Timeout
        
        while self._puzzle_state == 'setup' and time.time() < timeout:
            try:
                # Prüfe, ob das Brett korrekt aufgestellt ist
                if not self.game_engine._invalid_board_state:
                    # Brett ist korrekt! Spiele den ersten Zug
                    Log.info("Board setup complete! Playing first move...")
                    self._puzzle_state = 'playing'
                    
                    if self._current_puzzle and self._current_puzzle['moves']:
                        first_move = self._current_puzzle['moves'][0]
                        Log.info(f"Playing first move: {first_move}")
                        Centaur.play_computer_move(first_move)
                    
                    # Aktualisiere Web-UI nach Board-Setup
                    self.game_engine.update_web_ui({})
                    break
                
                time.sleep(0.5)
            except Exception as e:
                Log.exception(self._wait_for_board_setup, f"Error in board setup thread: {e}")
                break

    def key_callback(self, key: Enums.Btn):
        """Verarbeitet Tasteneingaben"""
        
        # Wenn Puzzle läuft: nur BACK zum Beenden erlauben
        if self._puzzle_state == 'playing':
            if key == Enums.Btn.BACK:
                Log.info("Player exited puzzle")
                self.stop()
                return True
            elif key == Enums.Btn.HELP:
                # Zeige Hinweis für den erwarteten Zug
                if self._current_move_index < len(self._current_puzzle['moves']):
                    if self.chessboard.turn == self._human_color:
                        expected_move = self._current_puzzle['moves'][self._current_move_index]
                        Centaur.light_move(expected_move)
                        Log.info(f"Hint shown: {expected_move}")
                return True
            return False

        # Wenn Brett aufgestellt wird: nur BACK zum Abbrechen
        if self._puzzle_state == 'setup':
            if key == Enums.Btn.BACK:
                Log.info("Player cancelled puzzle setup")
                self._puzzle_state = None
                self._menu_state = 'rating'
                self._update_menu_display()
                return True
            return False

        # Menü-Navigation
        if self._menu_state is None:
            # Splash screen
            if key == Enums.Btn.PLAY:
                self._menu_state = 'mate'
                self._update_menu_display()
                return True
            elif key == Enums.Btn.BACK:
                self.stop()
                return True
            return False

        elif self._menu_state == 'mate':
            if key == Enums.Btn.PLAY:
                self._menu_state = 'rating'
                self._update_menu_display()
                return True
            elif key == Enums.Btn.UP:
                mate_types = list(self._puzzle_categories.keys())
                current_idx = mate_types.index(self._current_mate_type)
                self._current_mate_type = mate_types[(current_idx + 1) % len(mate_types)]
                self._update_menu_display()
                return True
            elif key == Enums.Btn.DOWN:
                mate_types = list(self._puzzle_categories.keys())
                current_idx = mate_types.index(self._current_mate_type)
                self._current_mate_type = mate_types[(current_idx - 1) % len(mate_types)]
                self._update_menu_display()
                return True
            elif key == Enums.Btn.BACK:
                self._menu_state = None
                self.splash_screen()
                return True
            return False

        elif self._menu_state == 'rating':
            if key == Enums.Btn.PLAY:
                # Puzzle laden und Spiel starten
                puzzle = self.load_random_puzzle()
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
                
                # Starte das Spiel
                flags = Enums.BoardOption.CAN_UNDO_MOVES | Enums.BoardOption.RESUME_DISABLED
                Centaur.start_game(white=white, black=black, event="Lichess Puzzle Challenge", flags=flags)
                
                # Setze das Puzzle-FEN
                self.chessboard.set_fen(puzzle['fen'])
                
                # Initialisiere die Game-Engine manuell
                # (normalerweise würde der Thread warten, bis das Brett in Startposition ist)
                try:
                    self.game_engine._need_starting_position_check = False
                    self.game_engine._Engine__initialize()  # Ruft privaten __initialize auf
                    self.game_engine._invalid_board_state = True  # Brett stimmt noch nicht
                    self.game_engine._initialized = True
                    
                    # Aktualisiere den Board-State (zeigt falsche Felder mit LEDs)
                    self.game_engine._update_board_state(False)
                    
                    # Aktualisiere Web-UI mit dem Puzzle-FEN
                    self.game_engine.update_web_ui({})
                    
                    Log.info("Game engine initialized for puzzle")
                except Exception as e:
                    Log.exception(self.key_callback, f"Error initializing game engine: {e}")
                    Centaur.header("Engine error")
                    self.stop()
                    return False
                
                # Zeige das Brett auf dem Display
                SCREEN.get().draw_fen(puzzle['fen'], startrow=1.6)
                
                # Starte den Board-Setup-Thread
                self._puzzle_state = 'setup'
                self._board_setup_thread = threading.Thread(target=self._wait_for_board_setup, daemon=True)
                self._board_setup_thread.start()
                
                Log.info("Puzzle setup started - waiting for board to be arranged")
                return True
                
            elif key == Enums.Btn.UP:
                self._current_rating_index = (self._current_rating_index + 1) % len(self._rating_levels)
                self._update_menu_display()
                return True
            elif key == Enums.Btn.DOWN:
                self._current_rating_index = (self._current_rating_index - 1) % len(self._rating_levels)
                self._update_menu_display()
                return True
            elif key == Enums.Btn.BACK:
                self._menu_state = 'mate'
                self._update_menu_display()
                return True
            return False

        return False

    def event_callback(self, event: Enums.Event, outcome: Optional[chess.Outcome]):
        """Verarbeitet Game-Engine-Events"""
        
        # Spieler möchte beenden
        if event == Enums.Event.QUIT:
            Log.info("Plugin stopped by user")
            self.stop()
            return

        # Spiel beendet (Schachmatt, Stalemate, etc.)
        if event == Enums.Event.TERMINATION:
            if outcome and outcome.winner == self._human_color:
                Centaur.sound(Enums.Sound.VICTORY)
            else:
                Centaur.sound(Enums.Sound.GAME_LOST)
            return

        # Spieler oder Engine muss einen Zug machen
        if event == Enums.Event.PLAY:
            if self._current_puzzle is None or self._puzzle_state != 'playing':
                return
            
            turn = self.chessboard.turn
            current_player = "You" if turn == self._human_color else "Lichess Puzzle"
            Centaur.header(f"{current_player} {'W' if turn == chess.WHITE else 'B'}")
            
            # Spieler ist am Zug
            if turn == self._human_color:
                Log.info(f"Player turn. Expected move: {self._current_puzzle['moves'][self._current_move_index] if self._current_move_index < len(self._current_puzzle['moves']) else 'PUZZLE COMPLETE'}")
            
            # Engine ist am Zug
            else:
                if self._current_move_index < len(self._current_puzzle['moves']):
                    next_move = self._current_puzzle['moves'][self._current_move_index]
                    Log.info(f"Engine turn. Playing move: {next_move}")
                    Centaur.play_computer_move(next_move)

    def move_callback(self, uci_move: str, san_move: str, color: chess.Color, field_index: chess.Square) -> bool:
        """Verarbeitet Züge und prüft, ob sie korrekt sind"""
        
        if self._current_puzzle is None or self._puzzle_state != 'playing':
            return True

        Log.info(f"Move callback: {uci_move} by {'Player' if color == self._human_color else 'Engine'}")

        # Spielerzug - prüfe, ob er korrekt ist
        if color == self._human_color:
            if self._current_move_index >= len(self._current_puzzle['moves']):
                # Puzzle ist bereits gelöst
                Log.info("Puzzle already solved!")
                return True
            
            expected_move = self._current_puzzle['moves'][self._current_move_index]
            
            if uci_move != expected_move:
                # Falscher Zug - Framework macht automatisch pop() und lehnt ab
                Log.info(f"Wrong move! Expected: {expected_move}, got: {uci_move}")
                Centaur.sound(Enums.Sound.WRONG_MOVE)
                Centaur.header("Wrong move!")
                return False
            
            # Richtiger Zug
            Log.info(f"Correct move! {uci_move}")
            self._current_move_index += 1
            
            # Prüfe, ob Puzzle gelöst ist
            if self._current_move_index >= len(self._current_puzzle['moves']):
                Log.info("Puzzle solved!")
                Centaur.sound(Enums.Sound.VICTORY)
                Centaur.header("Puzzle solved!")
                time.sleep(2)
                self.stop()
            
            return True
        
        # Engine-Zug - akzeptiere ihn und erhöhe den Index
        else:
            Log.info(f"Engine move accepted: {uci_move}")
            self._current_move_index += 1
            return True

    def on_socket_request(self, data: dict) -> bool:
        """Verarbeitet Socket-Anfragen (Web-Interface)"""
        return False

    def on_stop_callback(self):
        """Wird aufgerufen, wenn das Plugin beendet wird"""
        self._puzzle_state = None
        self._current_puzzle = None
        Log.info("LichessPuzzleBot stopped")
