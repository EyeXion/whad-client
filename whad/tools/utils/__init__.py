import whad

from pkgutil import iter_modules
from importlib import import_module
from inspect import getdoc
from dataclasses import fields, is_dataclass
from scapy.config import conf

def list_implemented_sniffers():
    """Build a dictionnary of sniffers connector and configuration, by domain.
    """
    environment = {}

    # Iterate over modules
    for _, candidate_protocol,_ in iter_modules(whad.__path__):
        # If the module contains a sniffer connector and a sniffing module,
        # store the associated classes in the environment dictionary
        try:
            module = import_module("whad.{}.connector.sniffer".format(candidate_protocol))
            configuration_module = import_module("whad.{}.sniffing".format(candidate_protocol))
            environment[candidate_protocol] = {
                "sniffer_class":module.Sniffer,
                "configuration_class":configuration_module.SnifferConfiguration
            }
        except ModuleNotFoundError:
            pass
    # return the environment dictionary
    return environment

def get_sniffer_parameters(configuration_class):
    """
    Extract all parameters from a sniffer configuration class, with their name and associated documentation.

    :param configuration_class: sniffer configuration class
    :return: dict containing parameters for a given configuration class
    """
    parameters = {}
    # Extract documentation of every field in the configuration class
    fields_configuration_documentation = {
        i.replace(":param ","").split(":")[0] : i.replace(":param ","").split(":")[1]
        for i in getdoc(configuration_class).split("\n")
        if i.startswith(":param ")
    }

    # Iterate over the fields of the configuration class
    for field in fields(configuration_class):

        # If the field is a dataclass, process subfields
        if is_dataclass(field.type):
            # Extract documentation of every subfields
            subfields_configuration_documentation = {
                i.replace(":param ","").split(":")[0] : i.replace(":param ","").split(":")[1]
                for i in getdoc(field.type).split("\n")
                if i.startswith(":param ")
            }

            # Populate parameters dict with subfields configuration
            for subfield in fields(field.type):
                parameters["{}.{}".format(field.name,subfield.name)] = (
                    subfield.type,
                    subfield.default,
                    field.type,
                    (
                        subfields_configuration_documentation[subfield.name]
                        if subfield.name in subfields_configuration_documentation
                        else None
                    )
                )
        # if the field is not a dataclass, process it
        else:
            # Populate parameters dict with field configuration
            parameters[field.name] = (
                field.type,
                field.default,
                None,
                (
                    fields_configuration_documentation[field.name]
                    if field.name in fields_configuration_documentation
                    else None
                )
            )
    return parameters


def build_configuration_from_args(environment, args):
    """
    Build sniffer configuration from arguments provided via argparse.

    :param environment: environment
    :type environment: dict
    :param args: arguments provided by user
    :type args: :class:`argparse.ArgumentParser`
    """
    configuration = environment[args.domain]["configuration_class"]()
    subfields = {}
    for parameter in environment[args.domain]["parameters"]:
        base_class = None

        base_class = environment[args.domain]["parameters"][parameter][2]

        if base_class is None:
            try:
                setattr(configuration,parameter,getattr(args,parameter))
            except AttributeError:
                pass
        else:
            main, sub = parameter.split(".")
            if main not in subfields:
                subfields[main] = base_class()
            setattr(subfields[main], sub, getattr(args, parameter))


    for subfield in subfields:
        create = False
        for item in fields(subfields[subfield]):
            if getattr(subfields[subfield], item.name) is not None:
                create = True
                break
        if create:
            setattr(configuration, subfield, subfields[subfield])
        else:
            setattr(configuration, subfield, None)
    return configuration

def get_translator(protocol):
    """Get a translator according to a specific domain.
    """
    translator = None

    if protocol in ("zigbee", "rf4ce"):
        conf.dot15d4_protocol = protocol
    elif protocol == "esb":
        from whad.scapy.layers.unifying import unbind
        unbind()
    elif protocol == "unifying":
        from whad.scapy.layers.unifying import bind
        bind()
    # Iterate over modules
    for _, candidate_protocol,_ in iter_modules(whad.__path__):
        # If the module contains a sniffer connector,
        # store the associated translator in translator variable
        try:
            module = import_module("whad.{}.connector.sniffer".format(candidate_protocol))
            if candidate_protocol == protocol:
                translator = module.Sniffer.translator
                break
        except ModuleNotFoundError:
            pass
    # return the environment dictionary
    return translator
