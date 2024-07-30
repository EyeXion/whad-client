from prompt_toolkit import print_formatted_text, HTML
from scapy.all import Packet
from hexdump import hexdump

def success(message):
    """Display a success message in green (if color is enabled)
    """
    print_formatted_text(HTML('<aaa fg="#027923"><b>%s</b></aaa>' % message))

def warning(message):
    """Display a warning message in orange (if color is enabled)
    """
    print_formatted_text(HTML('<aaa fg="#e97f11">/!\\ <b>%s</b></aaa>' % message))

def error(message):
    """Display an error message in red (if color is enabled)
    """
    print_formatted_text(HTML('<ansired>[!] <b>{message}</b></ansired>').format(message=message))

def info(message):
    """Display an error info message in cyan (if color is enabled)
    """
    print_formatted_text(HTML('<ansicyan>[!] <b>%s</b></ansicyan>' % message))


def display_packet(pkt, show_metadata=True, format='repr'):
    """
    Display an packet according to the selected format.

    Four main types of formats can be used:
        * repr: scapy packet repr method (default)
        * show: scapy show method, "field" representation
        * hexdump: hexdump representation of the packet content
        * raw: raw received bytes

    :param  pkt:        Received Signal Strength Indicator
    :type   pkt:        :class:`scapy.packet.packet`
    """
    if isinstance(pkt, Packet):
        metadata = ""
        if hasattr(pkt, "metadata") and show_metadata:
            metadata = repr(pkt.metadata)
        # Process scapy show method format
        if format == "show":

            if show_metadata:
                print_formatted_text(
                    HTML("<b>{metadata}</b>").format(metadata=metadata)
                )
            pkt.show()

            if hasattr(pkt, "decrypted"):
                print_formatted_text(
                    HTML("<ansicyan>[i] Decrypted payload:</ansicyan>")
                )
                pkt.decrypted.show()

        # Process raw bytes format
        elif format == "raw":

            if show_metadata:
                print_formatted_text(
                    HTML("<b>{metadata}</b>").format(
                        metadata=metadata
                    )
                )

            print(bytes(pkt).hex())

            if hasattr(pkt, "decrypted"):
                print_formatted_text(
                    HTML("<ansicyan>[i] Decrypted payload:</ansicyan> {pkthex}").format(
                        pkthex=bytes(pkt.decrypted).hex()
                    )
                )

        # Process hexdump format
        elif format == "hexdump":
            if show_metadata:
                print_formatted_text(
                    HTML("<b>{metadata}</b>").format(metadata=metadata)
                )
            print_formatted_text(
                HTML("<i>{pkthex}</i>").format(pkthex=hexdump(bytes(pkt), result="return"))
            )
            if hasattr(pkt, "decrypted"):
                print_formatted_text(
                    HTML(
                        "<ansicyan>[i] Decrypted payload:</ansicyan>"
                    )
                )
                print_formatted_text(
                    HTML("<i>{pkthex}</i>").format(pkthex=hexdump(bytes(pkt.decrypted), result="return"))
                )
        # Process scapy repr format
        elif format == "repr":
            if show_metadata:
                print_formatted_text(
                    HTML("<b>{metadata}</b>").format(metadata=metadata)
                )
            print(repr(pkt))
            if hasattr(pkt, "decrypted"):
                print_formatted_text(
                    HTML("<ansicyan>[i] Decrypted payload:</ansicyan>")
                )
                print(repr(pkt.decrypted))
        print()
    # If it is not a packet, use repr method
    else:
        print(repr(pkt))

def display_event(event):
    """Display an event generated from a sniffer.
    """
    print_formatted_text(
        HTML("<ansicyan>[i] event: <b>{name}</b></ansicyan> {message}").format(
            name=event.name,
            message="("+event.message +")" if event.message is not None else ""
        )
    )

def format_analyzer_output(output, delimiter="\n", mode="human_readable"):
    if mode == "human_readable":
        if isinstance(output, bytes):
            return output.hex()
        elif isinstance(output, str):
            return output
        else:
            return str(output)
    elif mode == "raw":
        return output



def progress_bar(value=0, max_value=4, size=10):
    filled = int(size * (value / max_value))
    if filled > size:
        filled = size
    unfilled = size - filled
    return "\r\x1b[36m{filled_bar}\x1b[0m{unfilled_bar}".format(filled_bar=filled* "─", unfilled_bar=unfilled* "─")

def display_running_analyzers(analyzers):
    for analyzer_name, analyzer in self.selected_analyzers.items():
        print("\r" analyzer_name)
