"""WHAD server tool

This utility implements a server module, allowing to create a TCP proxy
which can be used to access a device remotely.
"""
from prompt_toolkit import print_formatted_text, HTML

from whad.common.monitors.pcap import PcapWriterMonitor
from whad.cli.app import CommandLineApp, ApplicationError, run_app
from scapy.all import *
from whad.device.unix import  UnixSocketConnector
from whad.device import Bridge
from whad.exceptions import WhadDeviceNotFound, WhadDeviceNotReady
from whad.cli.ui import error, warning, success, info, display_event, display_packet
from whad.tools.utils import get_translator, get_analyzers

import logging
import time
import sys


logger = logging.getLogger(__name__)
#logging.basicConfig(level=logging.DEBUG)

class WhadAnalyzeUnixSocketConnector(UnixSocketConnector):
    pass

def display_analyzers(analyzers):
    for domain, analyzers_list in analyzers.items():
        print_formatted_text(HTML("<b><ansicyan>Available analyzers: </ansicyan> {domain}</b>".format(domain=domain)))
        for analyzer_name, analyzer_class in analyzers_list.items():
            print_formatted_text(HTML("  <b>- {analyzer_name}</b> : {output}".format(analyzer_name=analyzer_name, output=", ".join(analyzer_class().output.keys()))))

        print()

class WhadAnalyzeApp(CommandLineApp):

    def __init__(self):
        """Application uses an interface and has commands.
        """
        super().__init__(
            description='WHAD analyze tool',
            interface=False,
            commands=False,
            input=CommandLineApp.INPUT_WHAD,
            output=CommandLineApp.OUTPUT_STANDARD
        )

        self.add_argument(
            'analyzer',
            help='Analyzer to use',
            nargs="*"
        )
        self.add_argument(
            '-l',
            '--list',
            action="store_true",
            help='List of available analyzers'
        )

    def on_packet(self, pkt):
        #print(repr(pkt))
        for analyzer_name, analyzer in self.selected_analyzers.items():
            analyzer.process_packet(pkt)
            #if analyzer.triggered:
            #    print("[i]", analyzer.__class__.__name__, "->", "triggered")
            if analyzer.completed:
                print("[i]", analyzer_name, "->", "completed (output=", repr(analyzer.output),")")
                #for pkt in analyzer.marked_packets:
                #    print("\t", repr(pkt))
                analyzer.reset()
                '''
                if "raw_audio" in analyzer.output:
                    import sys
                    sys.stdout.buffer.write(analyzer.output['raw_audio'])
                    sys.stdout.flush()
                    '''
    def run(self):
        # Launch pre-run tasks
        self.pre_run()

        if self.args.list:
            analyzers = get_analyzers()
            display_analyzers(analyzers)

        try:
            if self.is_piped_interface():
                interface = self.input_interface
            else:
                interface = self.interface

            if interface is not None:
                if not self.args.nocolor:
                    conf.color_theme = BrightTheme()

                parameters = self.args.__dict__

                connector = WhadAnalyzeUnixSocketConnector(interface)
                for parameter_name, parameter_value in parameters.items():
                    connector.add_parameter(parameter_name, parameter_value)

                self.selected_analyzers = {}
                for analyzer_name, analyzer_class in get_analyzers(self.args.domain).items():
                    if analyzer_name in self.args.analyzer or len(self.args.analyzer) == 0:
                        self.selected_analyzers[analyzer_name] = analyzer_class()

                connector.domain = self.args.domain
                connector.translator = get_translator(self.args.domain)(connector.hub)
                connector.format = connector.translator.format
                connector.on_packet = self.on_packet
                
                while True:
                    time.sleep(1)

        except KeyboardInterrupt:
            # Launch post-run tasks
            self.post_run()


def wanalyze_main():
    app = WhadAnalyzeApp()
    run_app(app)
