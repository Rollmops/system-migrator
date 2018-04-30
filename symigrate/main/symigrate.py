import logging
import sqlite3
import sys
from argparse import Namespace

from symigrate import SymigrateException
from symigrate.command.info_command import InfoCommand
from symigrate.command.migrate_command import MigrateCommand
from symigrate.commandline_parser_creator import CommandlineParserCreator
from symigrate.executed_migration_repository import ExecutedMigrationRepository
from symigrate.migration_file_matcher import MigrationFileMatcher
from symigrate.migration_merge_service import MigrationMergeService
from symigrate.migration_repository import MigrationRepository
from symigrate.migration_script_checker import MigrationScriptChecker
from symigrate.migration_script_runner import MigrationScriptRunner

LOGGER = logging.getLogger(__name__)


class CommandlineParsePhase:
    def __init__(self):
        commandline_parser_creator = CommandlineParserCreator()
        self.parser = commandline_parser_creator.create()

    def start(self, args):
        commandline_arguments = self.parser.parse_args(args)

        interface_creation_phase = InterfaceCreationPhase(commandline_arguments)
        interface_creation_phase.start()


class InterfaceCreationPhase:
    database_connection_hook = None

    def __init__(self, commandline_arguments: Namespace):
        self.commandline_arguments = commandline_arguments

    def start(self):
        logging.basicConfig(
            level=logging.getLevelName(self.commandline_arguments.logging_level.upper()),
            format=self.commandline_arguments.logging_format
        )

        database_connection = self._create_database_connection()

        main_phase = MainPhase(database_connection, self.commandline_arguments)

        try:
            main_phase.start()
        except SymigrateException as exception:
            LOGGER.error("%s: %s", type(exception).__name__, str(exception))
            exit(1)
        finally:
            LOGGER.debug("Closing database connection")
            database_connection.close()

    def _create_database_connection(self):
        LOGGER.debug("Opening database file '%s'", self.commandline_arguments.db_file_path)
        database_connection = InterfaceCreationPhase.database_connection_hook or \
                              sqlite3.connect(self.commandline_arguments.db_file_path).cursor().connection
        return database_connection


class MainPhase:
    out_stream_hook = None
    migration_script_checker_hook = None

    def __init__(self, database_connection: sqlite3.Connection, commandline_arguments: Namespace):
        self.commandline_arguments = commandline_arguments

        self.executed_migration_repository = ExecutedMigrationRepository(database_connection)
        migration_file_matcher = MigrationFileMatcher(
            commandline_arguments.migration_prefix,
            commandline_arguments.migration_separator,
            commandline_arguments.migration_suffix
        )

        migration_script_checker = MainPhase.migration_script_checker_hook or MigrationScriptChecker()

        self.migration_repository = MigrationRepository(
            commandline_arguments.migration_path,
            commandline_arguments.scope,
            commandline_arguments.encoding,
            migration_file_matcher,
            migration_script_checker
        )
        self.migration_merge_service = MigrationMergeService()
        self.migration_script_runner = MigrationScriptRunner()

    def start(self):
        self.executed_migration_repository.init()

        if self.commandline_arguments.command == "info":
            info_command = InfoCommand(
                self.executed_migration_repository,
                self.migration_repository,
                self.migration_merge_service,
                self.commandline_arguments.scope,
                out_stream=MainPhase.out_stream_hook or sys.stdout
            )
            info_command.run()
        elif self.commandline_arguments.command == "migrate":
            migrate_command = MigrateCommand(
                self.migration_repository,
                self.executed_migration_repository,
                self.migration_merge_service,
                self.migration_script_runner,
                self.commandline_arguments.scope,
                self.commandline_arguments.migration_path,
                out_stream=MainPhase.out_stream_hook or sys.stdout,
                single=self.commandline_arguments.single
            )
            migrate_command.run()


def main():
    commandline_parse_phase = CommandlineParsePhase()
    commandline_parse_phase.start(sys.argv[1:])


if __name__ == '__main__':
    main()
