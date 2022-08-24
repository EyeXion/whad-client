"""Security Management Protocol

BleSMP provides these different pairing strategies:

- "Just Works"

"""
from struct import pack
from binascii import hexlify


from scapy.layers.bluetooth import SM_Pairing_Request, SM_Pairing_Response, SM_Hdr,\
    SM_Confirm, SM_Random, SM_Failed
from whad.ble.crypto import LinkLayerCryptoManager, generate_random_value, c1, s1

from whad.ble.stack.smp.constants import *
from whad.ble.stack.smp.exceptions import SMInvalidParameterFormat

import logging
logger = logging.getLogger(__name__)

class SM_Peer(object):
    """
    SM_Peer stores all pairing-specific data regarding a peer.
    """


    def __init__(self, address):
        """Instanciate a SM_Peer.

        By default, peers are configured to only accept Legacy JustWorks pairing.
        """

        logger.info('Initiate SM_Peer object for peer %s' % address)

        # Peer address and address type
        self.__address = address

        # Key distribution (by default, corresponds to Legacy JustWorks)
        self.__kd_link_key = False
        self.__kd_sign_key = True
        self.__kd_enc_key = True
        self.__kd_id_key = True

        # Default security parameters
        self.__oob = False
        self.__bonding = True
        self.__mitm = False
        self.__lesc = False
        self.__keypress = False
        self.__ct2 = False
        self.__max_key_size = 16

        # Crypto parameters
        self.__confirm = None
        self.__rand = None
        self.__stk = None
        self.__ltk = None

        # Pairing method
        self.__pairing_method = PM_LEGACY_JUSTWORKS

        # IO Capabilities
        self.__io_cap = IOCAP_NOINPUT_NOOUTPUT

    @property
    def address(self):
        return self.__address.value

    @property
    def address_type(self):
        return self.__address.type

    def support_lesc(self):
        return self.__lesc

    def requires_bonding(self):
        return self.__bonding

    def support_mitm(self):
        return self.__mitm

    def set_security_parameters(self,
        lesc=None, mitm=None, bonding=None, keypress=None,
        ct2=None, max_key_size=None, oob=None):
        """Set security parameters for the current SM peer.

        :param lesc: Enable/disable LE Secure Connection for this peer
        :type lesc: bool, optional
        :param mitm: Enable/disable MITM for this peer
        :type mitm: bool, optional
        :param bonding: Enable/disable bonding for this peer
        :type bonding: bool, optional
        :param keypress: Enable/disable keypress notification for this peer
        :type keypress: bool, optional
        :param ct2: Enable/disable ct2 (h7 function support) for this peer
        :type ct2: bool, optional
        :param max_key_size: Set max key size for this peer
        :type ct2: int, optional
        :param oob: Use OOB data
        :type oob: bool, optional
        """
        if isinstance(lesc, bool):
            self.__lesc = lesc
        if isinstance(mitm, bool):
            self.__mitm = mitm
        if isinstance(bonding, bool):
            self.__bonding = bonding
        if isinstance(keypress, bool):
            self.__keypress = keypress
        if isinstance(ct2, bool):
            self.__ct2 = ct2
        if isinstance(oob, bool):
            self.__oob = oob
        if max_key_size is not None and isinstance(max_key_size, int):
            self.__max_key_size = max_key_size

    @property
    def iocap(self):
        """Return this peer IO capabilities
        """
        return self.__io_cap

    @iocap.setter
    def iocap(self, value):
        if value in [
            IOCAP_DISPLAY_ONLY,
            IOCAP_DISPLAY_YESNO,
            IOCAP_KEYBD_DISPLAY,
            IOCAP_KEYBD_ONLY,
            IOCAP_NOINPUT_NOOUTPUT
            ]:

            self.__io_cap = value
        else:
            raise SMInvalidParameterFormat


    @property
    def oob(self):
        return OOB_DISABLED if not self.__oob else OOB_ENABLED

    @property
    def authentication(self):
        """Rebuild authentication byte from internal status

        :return: Pairing Request/Response AuthReq value
        :rtype: int
        """
        flags = 0x00
        if self.__bonding:
            flags |= 0x01
        if self.__mitm:
            flags |= 0x04
        if self.__lesc:
            flags |= 0x08
        if self.__keypress:
            flags |= 0x10
        if self.__ct2:
            flags |= 0x20
        return flags

    ##
    # Key distribution
    ##

    def distribute_keys(self, link_key=False, sign_key=False, id_key=False, enc_key=False):
        """Mark keys to be distributed to peer.

        :param bool ltk: Will distribute LTK if set to True
        :param bool ediv: Will distribute EDIV if set to True
        :param bool rand: Will distribute RAND if set to True
        :param bool irk: Will distribute IRK if set to True
        :param bool address: Will distribute address if set to True
        :param bool csrk: Will distribute CSRK if set to True
        """
        self.__kd_link_key = link_key
        self.__kd_sign_key = sign_key
        self.__kd_id_key = id_key
        self.__kd_enc_key = enc_key

        if self.__pairing_method in [PM_LEGACY_JUSTWORKS, PM_LEGACY_PASSKEY]:
            keys = []
            if self.__kd_enc_key:
                keys.append('ltk, ediv, rand')
            if self.__kd_id_key:
                keys.append('irk')
            if self.__kd_sign_key:
                keys.append('csrk')
            logger.debug('Set distribute key for peer: %s' % (','.join(keys)))
        elif self.__pairing_method in [PM_LESC_JUSTWORKS, PM_LESC_NUMCOMP, PM_OOB]:
            keys=[]
            if self.__kd_id_key:
                keys.append('irk')
            if self.__kd_sign_key:
                keys.append('csrk')
            if self.__kd_link_key:
                keys.append('ltk')
            logger.debug('Set distribute key for peer: %s' % (','.join(keys)))

    def get_key_distribution(self):
        """Get the key distribution byte from the peer.

        This method is used to convert the internal key distribution model
        into an integer value that may be used in a Pairing Request or Pairing Response.

        :return: Key distribution byte
        :rtype: int
        """
        kd = 0x00
        if self.__kd_enc_key:
            kd |= 0x01
        if self.__kd_id_key:
            kd |= 0x02
        if self.__kd_sign_key:
            kd |= 0x04
        if self.__kd_link_key:
            kd |= 0x08
        return kd

    @property
    def max_key_size(self):
        return self.__max_key_size

    ##
    # Pairing method
    ##

    def set_pairing_method(self, pairing_method):
        """Set pairing method

        :param int pairing_method: Pairing method as defined in PM_* in BleSMP.
        """
        self.__pairing_method = pairing_method
        logger.info('Pairing method set to %d' % self.__pairing_method)

    @property
    def pairing_method(self):
        return self.__pairing_method


    ##
    # Crypto getters/setters/generators
    ##

    def generate_legacy_rand(self):
        """Generate a Rand value based on [Vol 3] Part H. Section 2.3.5.5
        """
        # Rand
        self.__rand = generate_random_value(128)
        logger.info('(%s) Generated RAND value: %s' % (
            self.__address,
            hexlify(self.__rand)
        ))

    @property
    def rand(self):
        return self.__rand

    @rand.setter
    def rand(self, value):
        """RAND must be 128-bit long byte array
        """
        if isinstance(value, bytes) and len(value) == 16:
            self.__rand = value
            logger.debug('(%s) Set RAND value: %s' % (
                self.__address,
                hexlify(value)
            ))
        else:
            raise SMInvalidParameterFormat()

    @property
    def confirm(self):
        return self.__confirm

    @confirm.setter
    def confirm(self, value):
        """CONFIRM must be 128-bit long byte array
        """
        if isinstance(value, bytes) and len(value) == 16:
            self.__confirm = value
            logger.debug('(%s) Set confirm value: %s' % (
                self.__address,
                hexlify(value)
            ))
        else:
            raise SMInvalidParameterFormat()

    def check_peer_confirm(self, tk, preq, pres, peer, initiator=True):
        """Check peer confirm value
        """
        logger.debug('(%s) RAND value: %s' % (
            self.__address,
            hexlify(self.__rand)
        ))
        logger.debug('(%s) CONFIRM value: %s' % (
            self.__address,
            hexlify(self.__confirm)
        ))
        # First, compute confirm based on rand
        if initiator:
            _confirm = self.compute_confirm_value(
                tk,
                preq,
                pres,
                self.address,
                self.address_type,
                peer.address,
                peer.address_type,
            )
        else:
            _confirm = self.compute_confirm_value(
                tk,
                preq,
                pres,
                peer.address,
                peer.address_type,
                self.address,
                self.address_type
            )
        return _confirm == self.get_confirm_value()


    def compute_confirm_value(self, tk, preq, pres, init_addr, init_addr_type, resp_addr, resp_addr_type):
        _confirm = c1(
            tk,
            self.__rand[::-1],
            pres[::-1],
            preq[::-1],
            pack('<B', init_addr_type),
            init_addr[::-1],
            pack('<B', resp_addr_type),
            resp_addr[::-1]
        )
        logger.info('(%s) Using RAND to compute confirm: %s' % (
            self.__address,
            hexlify(self.__rand)
        ))
        logger.info('(%s) Computed CONFIRM: %s' % (
            self.__address,
            hexlify(_confirm)
        ))
        return _confirm


class BleSMP(object):

    STATE_IDLE = 0x00
    STATE_PAIRING_REQ = 0x01
    STATE_PAIRING_RSP = 0x02
    STATE_LEGACY_PAIRING_CONFIRM_SENT = 0x03
    STATE_LEGACY_PAIRING_CONFIRM_RECVD = 0x04
    STATE_LEGACY_PAIRING_RANDOM_SENT = 0x05
    STATE_LEGACY_PAIRING_RANDOM_RECVD = 0x06
    STATE_LESC_PUBKEY_SENT = 0x07
    STATE_LESC_PUBKEY_RECVD = 0x08
    STATE_LESC_PAIRING_CONFIRM_SENT = 0x09
    STATE_LESC_PAIRING_RANDOM_SENT = 0x0A
    STATE_LESC_PAIRING_RANDOM_RECVD = 0x0B
    STATE_LESC_DHK_CHECK_SENT = 0x0C
    STATE_LESC_DHK_CHECK_RECVD = 0x0D

    def __init__(self, l2cap, justworks=True, lesc=False, capabilities=IOCAP_NOINPUT_NOOUTPUT):
        self.__l2cap = l2cap

        # Peers' states
        self.__initiator = None
        self.__responder = None

        # Current state
        self.__state = BleSMP.STATE_IDLE

        # Crypto manager
        self.__cm = None

        # Initiator Key Distribution
        self.__ikd = None

        # Responder Key Distribution
        self.__rkd = None

        # Pairing material
        self.__pairing_req = None
        self.__pairing_resp = None
        self.__tk = b'\x00'*16
        self.__stk = b'\x00'*16



    ##
    # Helpers
    ##

    def compute_confirm_value(self, tk, rand, preq, pres, initiator, responder):
        """Compute Confirm value as described in [Vol 3] Part H, Section 2.3.5.5

        This value is not ready to be set in a SM_Confirm packet as-is, it needs
        to be byte-reversed to be correctly decoded.

        :param bytes tk: Temporary Key
        :param bytes rand: Random to encrypt
        :param Packet preq: Pairing request
        :param Packet pres: Pairing response
        :param SM_Peer initiator: Pairing initiator
        :param SM_Peer responder: Pairing responder

        :return: Confirm value
        :rtype: bytes
        """
        logger.debug('TK=%s RAND=%s, PRES=%s PREQ=%s INITA_TYPE=%02x INITA=%s RESPA_TYPE=%02x RESPA=%s' % (
            hexlify(tk),
            hexlify(rand),
            hexlify(bytes(SM_Hdr()/pres)[::-1]),
            hexlify(bytes(SM_Hdr()/preq)[::-1]),
            initiator.address_type,
            hexlify(initiator.address[::-1]),
            responder.address_type,
            hexlify(responder.address[::-1])
        ))

        # Compute the confirm value for the provided parameters
        # We need to:
        # - convert `preq` to bytes in reverse order including SM_Hdr
        # - convert `pres` to bytes in reverse order including SM_Hdr
        # - reverse order of BD addresses
        # - pack address types as 8-bit data (prefixed by 7 zeroes)

        _confirm = c1(
            tk,
            rand,
            bytes(SM_Hdr()/pres)[::-1],
            bytes(SM_Hdr()/preq)[::-1],
            pack('<B', initiator.address_type),
            initiator.address[::-1],
            pack('<B', responder.address_type),
            responder.address[::-1]
        )
        return _confirm

    def check_initiator_confirm(self, tk):
        """Check initiator peer confirm value given a TK and the corresponding random value.

        :param SM_Peer: Peer to check
        :param bytes tk: Temporary Key
        :param Packet preq: Pairing request
        :param Packet pres: Pairing response
        :param SM_Peer initiator: Pairing initiator
        :param SM_Peer responder: Pairing responder
        """
        logger.debug('[check_initiator_confirm] RAND=%s' % hexlify(self.__initiator.rand))
        # Compute expected confirm value
        expected_confirm = self.compute_confirm_value(
            tk,
            self.__initiator.rand,
            self.__pairing_req,
            self.__pairing_resp,
            self.__initiator,
            self.__responder
        )
        logger.debug('[check_initiator_confirm] Computed CONFIRM=%s' % hexlify(expected_confirm))
        logger.debug('[check_initiator_confirm] Expected CONFIRM=%s' % hexlify(self.__initiator.confirm))

        # Compare with confirm value
        return (expected_confirm == self.__initiator.confirm)

    def check_responder_confirm(self, tk, preq, pres, initiator, responder):
        """Check responder peer confirm value given a TK and the corresponding random value.

        :param SM_Peer: Peer to check
        :param bytes tk: Temporary Key
        :param Packet preq: Pairing request
        :param Packet pres: Pairing response
        :param SM_Peer initiator: Pairing initiator
        :param SM_Peer responder: Pairing responder
        """
        logger.debug('[check_responder_confirm] RAND=%s' % hexlify(self.__initiator.rand))

        # Compute expected confirm value
        expected_confirm = self.compute_confirm_value(
            tk,
            self.__responder.rand,
            self.__pairing_req,
            self.__pairing_resp,
            self.__initiator,
            self.__responder
        )

        logger.debug('[check_initiator_confirm] Computed CONFIRM=%s' % hexlify(expected_confirm))
        logger.debug('[check_initiator_confirm] Expected CONFIRM=%s' % hexlify(self.__responder.confirm))

        # Compare with confirm value
        return (expected_confirm == self.__responder.confirm)


    def on_smp_packet(self, packet):
        """SMP packet reception callback

        This method dispatches every LE SMP packet received.

        :param Packet packet: Scapy packet containing SMP material
        """
        if SM_Pairing_Request in packet:
            self.on_pairing_request(packet.getlayer(SM_Pairing_Request))
        elif SM_Pairing_Response in packet:
            self.on_pairing_response(packet.getlayer(SM_Pairing_Response))
        elif SM_Confirm in packet:
            self.on_pairing_confirm(packet.getlayer(SM_Confirm))
        elif SM_Random in packet:
            self.on_pairing_random(packet.getlayer(SM_Random))
    
    def send(self, packet):
        self.__l2cap.send(SM_Hdr()/packet, channel=0x06)

    def on_pairing_request(self, pairing_req):
        """Method called when a pairing request is received.

        :param SM_Pairing_Request pairing_req: Pairing request packet
        """
        logger.info('Received Pairing Request')

        # Make sure we are in a state that allows this pairing request
        if self.__state == BleSMP.STATE_IDLE:
            logger.info('Pairing Request accepted, processing ...')

            # Save pairing request
            self.__pairing_req = pairing_req

            # We are definitely not the initiator but the responder
            self.__initiator = False
            self.__responder = SM_Peer(self.__l2cap.connection.local_peer)

            # Create the initiator SM_Peer instance
            # (along with all its parameters are defined in the pairing request)
            self.__initiator = SM_Peer(self.__l2cap.connection.remote_peer)
            self.__initiator.set_security_parameters(
                oob=(pairing_req.oob == 0x01),
                bonding=((pairing_req.authentication & 0x03) != 0),
                mitm=((pairing_req.authentication & 0x04) != 0),
                lesc=((pairing_req.authentication & 0x08) != 0),
                keypress=((pairing_req.authentication & 0x10) != 0),
                max_key_size = pairing_req.max_key_size
            )
            self.__initiator.iocap = pairing_req.iocap

            # Store responder key distribution options
            self.__responder.distribute_keys(
                enc_key = ((pairing_req.responder_key_distribution & 0x01) != 0),
                id_key = ((pairing_req.responder_key_distribution & 0x02) != 0),
                sign_key =((pairing_req.responder_key_distribution & 0x04) != 0),
                link_key = ((pairing_req.responder_key_distribution & 0x08) != 0)
            )

            # Send our pairing response
            pairing_resp = SM_Pairing_Response(
                iocap=self.__responder.iocap,
                oob=self.__responder.oob,
                authentication=self.__responder.authentication,
                max_key_size=self.__responder.max_key_size,
                initiator_key_distribution=self.__initiator.get_key_distribution(),
                responder_key_distribution=self.__responder.get_key_distribution()
            )

            # Save pairing response
            self.__pairing_resp = pairing_resp

            self.send(pairing_resp)

            # Update current state
            self.__state = BleSMP.STATE_PAIRING_REQ

        else:
            logger.info('Unexpected packet received, report error and return to idle.')
            
            # Notify error
            error = SM_Failed(
                reason = SM_ERROR_UNSPEC_REASON
            )
            self.send(error)

            # Return to IDLE mode
            self.__state = BleSMP.STATE_IDLE

    def on_pairing_confirm(self, confirm):
        """Method called whan a pairing confirm value is received.
        """
        # Make sure we have already sent a pairing request before
        logger.info('Received Pairing Confirm value')
        if self.__state == BleSMP.STATE_PAIRING_REQ:
            logger.info('Pairing Confirm value is expected, processing ...')

            # Store remote peer Confirm value (value is stored byte-reversed in Packet)
            self.__initiator.confirm = confirm.confirm[::-1]

            # Generate a RAND and compute CONFIRM
            self.__responder.generate_legacy_rand()
            self.__responder.confirm = self.compute_confirm_value(
                self.__tk,
                self.__responder.rand,
                self.__pairing_req,
                self.__pairing_resp,
                self.__initiator,
                self.__responder
            )
            logger.debug('[on_pairing_confirm] Computed CONFIRM=%s' % hexlify(self.__responder.confirm))

            # Send CONFIRM value (again, we need to reverse its bytes)
            confirm_value = SM_Confirm(
                confirm = self.__responder.confirm[::-1]
            )
            confirm_value.show()
            self.send(confirm_value)

            # Update current state
            self.__state = BleSMP.STATE_LEGACY_PAIRING_CONFIRM_SENT

        else:
            logger.info('Pairing Confirm dropped because current state is %d' % self.__state)

            # Notify error
            error = SM_Failed(
                reason = SM_ERROR_UNSPEC_REASON
            )
            self.send(error)

            # Return to IDLE mode
            self.__state = BleSMP.STATE_IDLE

    def on_pairing_random(self, random_pkt):
        """Handling random packet
        """
        logger.info('Received Pairing Random value')
        if self.__state == BleSMP.STATE_LEGACY_PAIRING_CONFIRM_SENT:
            logger.info('Pairing Random value is expected, processing ...')

            # Save initiator RAND (reverse byte order)
            self.__initiator.rand = random_pkt.random[::-1]

            self.check_initiator_confirm(self.__tk)
            if self.check_initiator_confirm(self.__tk):
                logger.info('Initiator CONFIRM successfully verified')
                # Send back our random
                rand_value = SM_Random(
                    random = self.__responder.rand[::-1]
                )
                self.send(rand_value)

                # Compute our stk
                self.__stk = s1(
                    self.__tk,
                    self.__responder.rand,
                    self.__initiator.rand
                )

                logger.debug('[on_pairing_random] STK=%s' % hexlify(self.__stk))

                # Next state
                self.__state = BleSMP.STATE_LEGACY_PAIRING_RANDOM_SENT

                # Notify connection that we successfully negociated STK and that
                # the corresponding material is available.
                self.__l2cap.connection.set_stk(self.__stk)
            else:
                logger.info('Invalid Initiator CONFIRM value (expected %s)' % (
                    hexlify(self.__initiator.confirm),
                ))

                # Send error
                error = SM_Failed(
                    reason = SM_ERROR_CONFIRM_VALUE_FAILED
                )
                self.send(error)

                # Return to IDLE
                self.__state = BleSMP.STATE_IDLE

        else:
            logger.info('Pairing Random dropped because current state is %d' % self.__state)

            # Notify error
            error = SM_Failed(
                reason = SM_ERROR_UNSPEC_REASON
            )
            self.send(error)

            # Return to IDLE mode
            self.__state = BleSMP.STATE_IDLE



def test_confirm():
    from whad.ble.bdaddr import BDAddress
    preq = b'\x07\x07\x10\x00\x00\x01\x01'
    pres = b'\x05\x00\x08\x00\x00\x03\x02'
    tk = b'\x00'*16
    initiator = SM_Peer(BDAddress('A1:A2:A3:A4:A5:A6', random=True))
    responder = SM_Peer(BDAddress('B1:B2:B3:B4:B5:B6'))
    rand = b'\x57\x83\xD5\x21\x56\xAD\x6F\x0E\x63\x88\x27\x4E\xC6\x70\x2E\xE0'
    confirm = b'\x1E\x1E\x3F\xEF\x87\x89\x88\xEA\xD2\xA7\x4D\xC5\xBE\xF1\x3B\x86'
    print('initiator: %s' % hexlify(initiator.address[::-1]))
    print(initiator.address_type)
    _confirm = c1(
        tk,
        rand,
        pres,
        preq,
        pack('<B', initiator.address_type),
        initiator.address[::-1],
        pack('<B', responder.address_type),
        responder.address[::-1]
    )

    print('Computed CONFIRM: %s' % hexlify(_confirm))
    print('Expected CONFIRM: %s' % hexlify(confirm))
