"""Protocol hub PHY factory  unit tests
"""
import pytest

from whad.protocol.whad_pb2 import Message
from whad.hub.phy import PhyDomain, SetAskMod, SetBpskMod, SetFskMod, SetGfskMod, \
    SetLoRaMod, SetMskMod, SetQpskMod, Set4FskMod, SpreadingFactor, CodingRate, \
    SetFreq, GetSupportedFreqs, SupportedFreqRanges, SniffMode, JamMode, Jammed, \
    MonitorMode, MonitoringReport, Jamming, SetDatarate, SetEndianness, SetPacketSize, \
    SetTxPower, SetSyncWord, TxPower, SendPacket, SendRawPacket, PacketReceived, \
    RawPacketReceived, Timestamp

class TestPhyDomainFactory(object):
    """Test PHY factory
    """

    @pytest.fixture
    def factory(self):
        return PhyDomain(1)
    
    def test_set_ask_mod(self, factory: PhyDomain):
        """Check creation of SetAskMod message
        """
        msg = factory.createSetAskMod(ook=False)
        assert isinstance(msg, SetAskMod)
        assert msg.ook == False

    def test_set_bpsk_mod(self, factory: PhyDomain):
        """Check creation of SetBpskMod message
        """
        msg = factory.createSetBpskMod()
        assert isinstance(msg, SetBpskMod)

    def test_set_fsk_mod(self, factory: PhyDomain):
        """Check creation of SetFskMod message
        """
        msg = factory.createSetFskMod(125000)
        assert isinstance(msg, SetFskMod)
        assert msg.deviation == 125000

    def test_set_gfsk_mod(self, factory: PhyDomain):
        """Check creation of SetGfskMod message
        """
        msg = factory.createSetGfskMod(125000)
        assert isinstance(msg, SetGfskMod)
        assert msg.deviation == 125000
    
    def test_set_msk_mod(self, factory: PhyDomain):
        """Check creation of SetMskMod message
        """
        msg = factory.createSetMskMod(125000)
        assert isinstance(msg, SetMskMod)
        assert msg.deviation == 125000

    def test_set_qpsk_mod(self, factory: PhyDomain):
        """Check creation of SetQpskMod message
        """
        msg = factory.createSetQpskMod(True)
        assert isinstance(msg, SetQpskMod)
        assert msg.offset == True

    def test_set_4fsk_mod(self, factory: PhyDomain):
        """Check creation of Set4FskMod message
        """
        msg = factory.createSet4FskMod(125000)
        assert isinstance(msg, Set4FskMod)
        assert msg.deviation == 125000

    def test_set_lora_mod(self, factory: PhyDomain):
        """Check creation of SetLoRaMod message
        """
        msg = factory.createSetLoRaMod(250000, SpreadingFactor.SF7, CodingRate.CR48, 8)
        assert isinstance(msg, SetLoRaMod)
        assert msg.bandwidth == 250000
        assert msg.cr == CodingRate.CR48
        assert msg.sf == SpreadingFactor.SF7
        assert msg.preamble_length == 8
        assert msg.explicit_mode == True
        assert msg.invert_iq == False
        assert msg.enable_crc == True

    def test_set_freq(self, factory: PhyDomain):
        """Check creation of SetFreq message
        """
        msg = factory.createSetFreq(2440000000)
        assert isinstance(msg, SetFreq)
        assert msg.frequency == 2440000000

    def test_get_supported_freqs(self, factory: PhyDomain):
        """Check creation of GetSupportedFreqs message
        """
        msg = factory.createGetSupportedFreqs()
        assert isinstance(msg, GetSupportedFreqs)

    def test_supported_freqs(self, factory: PhyDomain):
        """Check creation of SetFreq message
        """
        msg = factory.createSupportedFreqRanges([
            (433000000, 468000000),
            (868000000, 890000000)
        ])
        assert isinstance(msg, SupportedFreqRanges)
        assert len(msg.ranges) == 2
        assert msg.ranges[0].start == 433000000
        assert msg.ranges[0].end == 468000000
        assert msg.ranges[1].start == 868000000
        assert msg.ranges[1].end == 890000000

    def test_sniff_mode(self, factory: PhyDomain):
        """Check creation of SniffMode message
        """
        msg = factory.createSniffMode(False)
        assert isinstance(msg, SniffMode)
        assert msg.iq_stream == False

    def test_jam_mode(self, factory: PhyDomain):
        """Check creation of JamMode message
        """
        msg = factory.createJamMode(Jamming.CONTINUOUS)
        assert isinstance(msg, JamMode)
        assert msg.mode == Jamming.CONTINUOUS

    def test_monitor_mode(self, factory: PhyDomain):
        """Check creation of MonitorMode message
        """
        msg = factory.createMonitorMode()
        assert isinstance(msg, MonitorMode)

    def test_monitoring_report(self, factory: PhyDomain):
        """Check creation of MonitorMode message
        """
        msg = factory.createMonitoringReport(1234, [1, 24, 12, 5])
        assert isinstance(msg, MonitoringReport)
        assert msg.timestamp == 1234
        assert len(msg.reports) == 4
        assert msg.reports[0] == 1
        assert msg.reports[3] == 5

    def test_datarate(self, factory: PhyDomain):
        """Check creation of SetDatarate message
        """
        msg = factory.createSetDatarate(2000)
        assert isinstance(msg, SetDatarate)
        assert msg.rate == 2000

    def test_endianness(self, factory: PhyDomain):
        """Check creation of SetEndianness message
        """
        msg = factory.createSetEndianness(True)
        assert isinstance(msg, SetEndianness)
        assert msg.endianness == 1

    def test_packet_size(self, factory: PhyDomain):
        """Check creation of SetPacketSize message
        """
        msg = factory.createSetPacketSize(32)
        assert isinstance(msg, SetPacketSize)
        assert msg.packet_size == 32

    def test_sync_word(self, factory: PhyDomain):
        """Check creation of SetSyncWord message
        """
        msg = factory.createSetSyncWord(b"AAAA")
        assert isinstance(msg, SetSyncWord)
        assert msg.sync_word == b"AAAA"

    def test_tx_power(self, factory: PhyDomain):
        """Check creation of SetTxPower message
        """
        msg = factory.createSetTxPower(TxPower.MEDIUM)
        assert isinstance(msg, SetTxPower)
        assert msg.power == TxPower.MEDIUM

    def test_send_packet(self, factory: PhyDomain):
        """Check creation of SetTxPower message
        """
        msg = factory.createSendPacket(b"HELLOWORLD")
        assert isinstance(msg, SendPacket)
        assert msg.packet == b"HELLOWORLD"

    def test_send_raw_packet(self, factory: PhyDomain):
        """Check creation of SetTxPower message
        """
        msg = factory.createSendRawPacket([1, -3, 2, 5])
        assert isinstance(msg, SendRawPacket)
        assert len(msg.iq) == 4
        assert msg.iq[0] == 1
        assert msg.iq[2] == 2

    def test_pkt_recvd(self, factory: PhyDomain):
        """Check creation of PacketReceived message
        """
        msg = factory.createPacketReceived(2400000000, b"FOOBAR", timestamp=Timestamp(1234, 9876))
        assert isinstance(msg, PacketReceived)
        assert msg.frequency == 2400000000
        assert msg.packet == b"FOOBAR"
        assert msg.rssi is None
        assert msg.timestamp.sec == 1234
        assert msg.timestamp.usec == 9876

    def test_raw_pkt_recvd(self, factory: PhyDomain):
        """Check creation of SetTxPower message
        """
        msg = factory.createRawPacketReceived(2400000000, b"", timestamp=Timestamp(1234, 9876), \
                                              iq=[1,2,3,4], rssi=-58)
        assert isinstance(msg, RawPacketReceived)
        assert msg.frequency == 2400000000
        assert msg.packet == b""
        assert msg.rssi == -58
        assert msg.timestamp.sec == 1234
        assert msg.timestamp.usec == 9876
        assert len(msg.iq) == 4
        assert msg.iq[1] == 2
