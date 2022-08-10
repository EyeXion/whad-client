# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: protocol/device.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x15protocol/device.proto\x12\tdiscovery\"\x12\n\x10\x44\x65viceResetQuery\"\x11\n\x0f\x44\x65viceReadyResp\"\"\n\x11SetTransportSpeed\x12\r\n\x05speed\x18\x01 \x01(\r\"\xe0\x01\n\x0e\x44\x65viceInfoResp\x12\x0c\n\x04type\x18\x01 \x01(\r\x12\r\n\x05\x64\x65vid\x18\x02 \x01(\x0c\x12\x15\n\rproto_min_ver\x18\x03 \x01(\r\x12\x11\n\tmax_speed\x18\x04 \x01(\r\x12\x11\n\tfw_author\x18\x05 \x01(\x0c\x12\x0e\n\x06\x66w_url\x18\x06 \x01(\x0c\x12\x18\n\x10\x66w_version_major\x18\x07 \x01(\r\x12\x18\n\x10\x66w_version_minor\x18\x08 \x01(\r\x12\x16\n\x0e\x66w_version_rev\x18\t \x01(\r\x12\x18\n\x0c\x63\x61pabilities\x18\n \x03(\rB\x02\x10\x01\"B\n\x14\x44\x65viceDomainInfoResp\x12\x0e\n\x06\x64omain\x18\x01 \x01(\r\x12\x1a\n\x12supported_commands\x18\x02 \x01(\x04\"$\n\x0f\x44\x65viceInfoQuery\x12\x11\n\tproto_ver\x18\x01 \x01(\r\"\'\n\x15\x44\x65viceDomainInfoQuery\x12\x0e\n\x06\x64omain\x18\x01 \x01(\r\"\xfd\x02\n\x07Message\x12\x32\n\x0breset_query\x18\x01 \x01(\x0b\x32\x1b.discovery.DeviceResetQueryH\x00\x12\x30\n\nready_resp\x18\x02 \x01(\x0b\x32\x1a.discovery.DeviceReadyRespH\x00\x12\x30\n\ninfo_query\x18\x03 \x01(\x0b\x32\x1a.discovery.DeviceInfoQueryH\x00\x12.\n\tinfo_resp\x18\x04 \x01(\x0b\x32\x19.discovery.DeviceInfoRespH\x00\x12\x38\n\x0c\x64omain_query\x18\x05 \x01(\x0b\x32 .discovery.DeviceDomainInfoQueryH\x00\x12\x36\n\x0b\x64omain_resp\x18\x06 \x01(\x0b\x32\x1f.discovery.DeviceDomainInfoRespH\x00\x12\x31\n\tset_speed\x18\x07 \x01(\x0b\x32\x1c.discovery.SetTransportSpeedH\x00\x42\x05\n\x03msg*\xc9\x01\n\x06\x44omain\x12\x0f\n\x0b_DomainNone\x10\x00\x12\x0e\n\x07Generic\x10\x80\x80\x80\x08\x12\x10\n\tBtClassic\x10\x80\x80\x80\x10\x12\x0b\n\x04\x42tLE\x10\x80\x80\x80\x18\x12\r\n\x06Zigbee\x10\x80\x80\x80 \x12\x10\n\tSixLowPan\x10\x80\x80\x80(\x12\n\n\x03\x45sb\x10\x80\x80\x80\x30\x12\x17\n\x10LogitechUnifying\x10\x80\x80\x80\x38\x12\r\n\x06Mosart\x10\x80\x80\x80@\x12\n\n\x03\x41NT\x10\x80\x80\x80H\x12\x0f\n\x08\x41NT_Plus\x10\x80\x80\x80P\x12\r\n\x06\x41NT_FS\x10\x80\x80\x80X*=\n\nDeviceType\x12\x12\n\x0e\x45sp32BleFuzzer\x10\x00\x12\r\n\tButterfly\x10\x01\x12\x0c\n\x08\x42tleJack\x10\x02*\xc5\x01\n\nCapability\x12\x0c\n\x08_CapNone\x10\x00\x12\x08\n\x04Scan\x10\x01\x12\t\n\x05Sniff\x10\x02\x12\n\n\x06Inject\x10\x04\x12\x07\n\x03Jam\x10\x08\x12\n\n\x06Hijack\x10\x10\x12\x08\n\x04Hook\x10 \x12\x0e\n\nMasterRole\x10@\x12\x0e\n\tSlaveRole\x10\x80\x01\x12\x0e\n\tNoRawData\x10\x80\x02\x12\x12\n\rEndDeviceRole\x10\x81\x02\x12\x14\n\x0f\x43oordinatorRole\x10\x82\x02\x12\x0f\n\nRouterRole\x10\x84\x02\x62\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'protocol.device_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  _DEVICEINFORESP.fields_by_name['capabilities']._options = None
  _DEVICEINFORESP.fields_by_name['capabilities']._serialized_options = b'\020\001'
  _DOMAIN._serialized_start=870
  _DOMAIN._serialized_end=1071
  _DEVICETYPE._serialized_start=1073
  _DEVICETYPE._serialized_end=1134
  _CAPABILITY._serialized_start=1137
  _CAPABILITY._serialized_end=1334
  _DEVICERESETQUERY._serialized_start=36
  _DEVICERESETQUERY._serialized_end=54
  _DEVICEREADYRESP._serialized_start=56
  _DEVICEREADYRESP._serialized_end=73
  _SETTRANSPORTSPEED._serialized_start=75
  _SETTRANSPORTSPEED._serialized_end=109
  _DEVICEINFORESP._serialized_start=112
  _DEVICEINFORESP._serialized_end=336
  _DEVICEDOMAININFORESP._serialized_start=338
  _DEVICEDOMAININFORESP._serialized_end=404
  _DEVICEINFOQUERY._serialized_start=406
  _DEVICEINFOQUERY._serialized_end=442
  _DEVICEDOMAININFOQUERY._serialized_start=444
  _DEVICEDOMAININFOQUERY._serialized_end=483
  _MESSAGE._serialized_start=486
  _MESSAGE._serialized_end=867
# @@protoc_insertion_point(module_scope)
