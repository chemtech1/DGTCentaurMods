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

import chess, random, chess.engine

from DGTCentaurMods.classes.Plugin import Plugin, Centaur, TPlayResult
from DGTCentaurMods.consts import Enums, fonts

from typing import Optional

HUMAN_COLOR = chess.WHITE

# The plugin must inherits of the Plugin class.
# Filename must match the class name.



#----------------------------------------------------------
# Chess engines
#CHESS_ENGINES = Centaur.get_chess_engines()
# Centaur.play_computer_move(str(result.move))
# Centaur.configure_chess_engine(engine_name, self._engines_options_sequence[self._sequence_index])
# Centaur.set_main_chess_engine("stockfish")
# Centaur.configure_main_chess_engine({"UCI_Elo": 2200})

#Centaur.set_main_chess_engine("ct800")

#    self._adjust_chess_engine(1800)




# def engine_move_callback(result:TPlayResult):

     #              Centaur.play_computer_move(str(result.move))

                    # Position needs to be evaluated again.
        #            self._evaluate_position_and_adjust_level()

                # Computer is going to play asynchronously.
                # (in the meantime, user can takeback or force a move...)
 #               Centaur.request_chess_engine_move(engine_move_callback)

 #--------------------------------------------------------------------------
class chess960(Plugin):

     def __init__(self, id: str):
        super().__init__(id)
        self.engine = chess.engine.SimpleEngine.popen_uci("/opt/DGTCentaur/engines/stockfish")

    """

    # Constructor for initialization stuff
    # The id is the name of the plugin/class
    def __init__(self, id:str):
        super().__init__(id)

    # This function is automatically invoked when
    # the user launches the plugin.
    def start(self):
        super().start()

    # This function is (automatically) invoked when
    # the user stops the plugin.
    def stop(self):
        # Back to the main menu.
        super().stop()

    # When exists, this function is automatically invoked
    # when the player physically plays a move.
    def move_callback(self, uci_move:str, san_move:str, color:chess.Color, field_index:chess.Square):
        
        # Nothing to do there...

        if color == (not HUMAN_COLOR):
            # Black move is accepted
            return True

        # White move is accepted
        return True

    """

    # This function is automatically invoked each
    # time the player pushes a key.
    # Except the BACK key which is handled by the engine.
    def key_callback(self, key:Enums.Btn):

        # If the user pushes HELP,
        # we display an hint using Stockfish engine.
        if key == Enums.Btn.HELP:
            Centaur.hint()

            # Key has been handled.
            return True
        
        # Key can be handled by the engine.
        return False
        
    # When exists, this function is automatically invoked
    # when the game engine state is affected.
    def event_callback(self, event:Enums.Event, outcome:Optional[chess.Outcome]):

        # If the user chooses to leave,
        # we quit the plugin.
        if event == Enums.Event.QUIT:
            self.stop()

        if event == Enums.Event.PLAY:

            turn = self.chessboard.turn

            current_player = "You" if turn == chess.WHITE else "Random bot"

            # We display the board header.
            Centaur.header(f"{current_player} {'W' if turn == chess.WHITE else 'B'}")

            if turn == (not HUMAN_COLOR):

                # We choose a random move
                #uci_move = str(random.choice(list(self.chessboard.legal_moves)))

                #Centaur.play_computer_move(uci_move)
                #Centaur.play_computer_move(str(result.move))
                result = self.engine.play(self.chessboard, chess.engine.Limit(time=2.0))
                Centaur.play_computer_move(result.move.uci())

                #def engine_move_callback(result:TPlayResult):

                 #   Centaur.play_computer_move(str(result.move))

                    # Position needs to be evaluated again.
                 #   self._evaluate_position_and_adjust_level()

                # Computer is going to play asynchronously.
                # (in the meantime, user can takeback or force a move...)
             #   Centaur.request_chess_engine_move(engine_move_callback)

















     # When exists, this function is automatically invoked
     # at start, after splash screen, on PLAY button.
    def on_start_callback(self, key:Enums.Btn) -> bool:

        # Start a new game.
        Centaur.start_game(
            white="You", 
            black="Random bot", 
            event="Bots chess event 2024",
            flags=Enums.BoardOption.CAN_UNDO_MOVES)
        
        # Game started.
        return True

     # When exists, this function is automatically invoked
     # when the plugin starts.
    def splash_screen(self) -> bool:

        print = Centaur.print

        Centaur.clear_screen()

        print("RANDOM", row=2)
        print("BOT", font=fonts.DIGITAL_FONT, row=4)
        print("Push PLAY", row=8)
        print("to")
        print("start")
        print("the game!")

        # The splash screen is activated.
        return True
