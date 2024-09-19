"""
Implementation of the Confiruation Server And Client Models
Mesh Protocol Specificiation Section 4.4.1 and 4.4.2
"""

from whad.bt_mesh.models import (
    ModelServer,
    Element,
)


from whad.scapy.layers.bt_mesh import *

from whad.bt_mesh.models.states import SecureNetworkBeaconState, NetKeyListState
from whad.bt_mesh.stack.utils import (
    get_address_type,
    UNASSIGNED_ADDR_TYPE,
    UNICAST_ADDR_TYPE,
    GROUP_ADDR_TYPE,
    key_indexes_to_packet_encoding,
)


from whad.bt_mesh.crypto import (
    compute_virtual_addr_from_label_uuid,
    NetworkLayerCryptoManager,
    UpperTransportLayerAppKeyCryptoManager,
)


# Mesh PRT Spec Table 4.10 Section 4.2.2.2
_FIELD_VALUE_TO_ELEMENT_OFFSET = {0: 0, 1: 1, 2: 2, 3: 3, 4: -4, 5: -3, 6: -2, 7: -1}
_ELEMENT_OFFSET_TO_FIELD_VALUE = {
    v: k for k, v in _FIELD_VALUE_TO_ELEMENT_OFFSET.items()
}


class CompositionDataState(object):
    """
    Composition Data state containing the page 0 and page 1 only (for now)
    Should be initialised ONCE and never change until term of node.
    One per sub network (for now not supported)
    """

    def __init__(self):
        pass

    def init_page0(self, cid, pid, vid, crpl, features, elements: list[Element]):
        """
        Initializes the Page 0 of the Comosition Data State.
        Mesh PRT Specificiation Section 4.2.2.1

        :param cid: Company Identifier (2 bytes)
        :type cid: bytes
        :param pid: Product Identifier (2 bytes)
        :type pid: bytes
        :param vid: Vendor assigned product software version Identifier (2 bytes)
        :type vid: bytes
        :param crpl: Minimum number of Replay Protection List entries
        :type crpl: int
        :param features: Bit field of devices features (Mesh PRT spec Section Table 4.3)
        :type features: bytesœ&
        :param elements: List of elements that live on the network
        :type elements: List[Elements]
        """
        # we compute the bytes object of the page to use in the scapy packet directly since it doesnt change
        self.p0_data = cid + pid + vid + crpl + features

        elements_field = b""
        for element in elements:
            self.elements_fields = (
                elements_field
                + element.loc.to_bytes(2, "big")
                + element.model_count.to_bytes(1)
                + element.vnd_model_count.to_bytes(1)
            )
            for model_id in element.models.keys():
                self.elements_fields = elements_field + model_id
            # no vendor models yet so nothing

        self.p0_data = self.p0_data + elements_field

    def get_p0_data(self):
        return self.p0_data

    def __p1_add_model(self, model, fmt):
        """
        Returns the model data for the Composition Page 1
        Mesh PRT Spec Section 4.2.2.2 Table 4.9/4.11

        :param model: Model to add
        :type model: Model
        :param fmt: Format value to use
        :type fmt: int
        """

        if not isinstance(model, ModelServer):
            return int(0).to_bytes(1, "big")
        else:
            model_data = (
                (len(model.relationships) << 2)
                + (fmt << 1)
                + int(model.corresponding_group_id is not None)
            ).to_bytes(1, "big")
            if model.corresponding_group_id is not None:
                model_data += model.corresponding_group_id.to_bytes(1, "big")

            for rel in model.relationships:
                if fmt == 0:
                    offset = _ELEMENT_OFFSET_TO_FIELD_VALUE[
                        rel.elem_ext.element_addr - rel.elem_base.element_addr
                    ]
                    model_data += (
                        (rel.elem_ext.get_index_of_model(rel.mod_ext) << 3)
                        + (offset & 0x07)
                    ).to_bytes(1, "big")
                else:
                    offset = rel.elem_ext.element_addr - rel.elem_base.element_addr
                    model_data = offset.to_bytes(
                        1, "big", signed=True
                    ) + rel.elem_ext.get_index_of_model(rel.mod_ext).to_bytes(1, "big")

                return model_data

    def init_page1(self, elements: list[Element]):
        """
        Inits the Page 1 of the CompositionData State.
        Mesh PRT Spec Section 4.2.2.2

        :param elements: List of elements on the network (in order !!)
        :type elements: List[Elements]
        :param model_relationships: All the model model_relationships on the network
        :type model_relationships: List(ModelRelationship)
        """

        self.p1_data = b""
        # depending on the number of elements, we dont use the same format in model data
        # Mesh PRT Spec Section 4.2.2.2 Table 4.9 or 4.11 (should create a scapy packet)

        if len(elements) > 4:
            fmt = 1
        else:
            fmt = 0

        for element in elements:
            element_data = b""
            element_data = element.model_count.to_bytes(
                1
            ) + element.vnd_model_count.to_bytes(1)

            for model in element.models.values():
                element_data += self.__p1_add_model(model, fmt)

            self.p1_data += element_data

    def get_p1_data(self):
        return self.p1_data


class ConfigurationModelServer(ModelServer):
    def __init__(self, element_addr):
        super().__init__(model_id=0x0000, element_addr=element_addr)

        self.handlers[0x8009] = self.on_secure_beacon_get
        self.handlers[0x800A] = self.on_secure_beacon_set
        self.handlers[0x8008] = self.on_composition_data_get
        self.handlers[0x800C] = self.on_default_ttl_get
        self.handlers[0x800D] = self.on_default_ttl_set
        self.handlers[0x8012] = self.on_gatt_proxy_get
        self.handlers[0x8013] = self.on_gatt_proxy_set
        self.handlers[0x800F] = self.on_friend_get
        self.handlers[0x0010] = self.on_friend_set
        self.handlers[0x8026] = self.on_relay_get
        self.handlers[0x8027] = self.on_relay_set
        self.handlers[0x8018] = self.on_model_publication_get
        self.handlers[0x801A] = self.on_model_publication_set
        self.handlers[0x03] = self.on_model_publication_set
        self.handlers[0x801B] = self.on_model_subscription_add
        self.handlers[0x801C] = self.on_model_subscription_delete
        self.handlers[0x801D] = self.on_model_subscription_delete_all
        self.handlers[0x801E] = self.on_model_subscription_overwrite
        self.handlers[0x8020] = self.on_model_subscription_virtual_address_add
        self.handlers[0x8021] = self.on_model_subscription_virtual_address_delete
        self.handlers[0x8022] = self.on_model_subscription_virtual_overwrite
        self.handlers[0x8029] = self.on_model_subscription_sig_get
        self.handlers[0x802B] = self.on_model_subscription_sig_get
        self.handlers[0x8040] = self.on_net_key_add
        self.handlers[0x8045] = self.on_net_key_update
        self.handlers[0x8041] = self.on_net_key_delete
        self.handlers[0x8042] = self.on_net_key_get
        self.handlers[0x00] = self.on_app_key_add
        self.handlers[0x01] = self.on_app_key_update
        self.handlers[0x8000] = self.on_app_key_delete
        self.handlers[0x8001] = self.on_app_key_get
        self.handlers[0x803D] = self.on_model_to_app_key_bind
        self.handlers[0x803F] = self.on_model_to_app_key_unbind
        self.handlers[0x804B] = self.on_sig_model_to_app_key_get
        self.handlers[0x804D] = self.on_vendor_model_to_app_key_get
        self.handlers[0x8046] = self.on_node_identity_get
        self.handlers[0x8047] = self.on_node_identity_set
        self.handlers[0x8049] = self.on_node_reset
        self.handlers[0x8015] = self.on_key_refresh_phase_get
        self.handlers[0x8016] = self.on_key_refresh_phase_set
        self.handlers[0x8038] = self.on_heartbeat_publication_get
        self.handlers[0x8039] = self.on_heartbeat_publication_set
        self.handlers[0x803A] = self.on_heartbeat_subscription_get
        self.handlers[0x803B] = self.on_heartbeat_subscription_set
        self.handlers[0x802D] = self.on_lpn_poll_timeout_get
        self.handlers[0x8023] = self.on_network_transmit_get
        self.handlers[0x8024] = self.on_network_transmit_set

    def on_secure_beacon_get(self, message):
        value = self.global_states_manager.get_state(
            "secure_network_beacon"
        ).get_value()
        response = BTMesh_Model_Config_Beacon_Status(beacon=value)
        return response

    def on_secure_beacon_set(self, message):
        self.global_states_manager.get_state("secure_network_beacon").set_value(
            message.beacon
        )
        value = self.global_states_manager.get_value(
            "secure_network_beacon"
        ).get_value()
        response = BTMesh_Model_Config_Beacon_Status(beacon=value)
        return response

    # TODO
    def on_composition_data_get(self, message):
        if message.page == 0:
            p0_data = self.states["composition_data"].get_p0_data()
            response = BTMesh_Model_Config_Composition_Data_Status(page=0, data=p0_data)
        elif message.page == 1:
            p1_data = self.states["composition_data"].get_p1_data()
            response = BTMesh_Model_Config_Composition_Data_Status(page=1, data=p1_data)
        # if composition page not supported, send highest page number supported
        else:
            response = BTMesh_Model_Config_Composition_Data_Status(page=0x01)
        return response

    def on_default_ttl_get(self, message):
        ttl = self.global_states_manager.get_state("default_ttl").get_value()
        response = BTMesh_Model_Config_Default_TTL_Status(ttl=ttl)
        return response

    def on_default_ttl_set(self, message):
        ttl = message.ttl
        self.global_states_manager.get_state("default_ttl").set_value(ttl)
        response = BTMesh_Model_Config_Default_TTL_Status(ttl=ttl)
        return response

    def on_gatt_proxy_get(self, message):
        gatt_proxy = self.global_states_manager.get_state("gatt_proxy").get_value()
        response = BTMesh_Model_Config_Gatt_Proxy_Status(gatt_proxy=gatt_proxy)
        return response

    def on_gatt_proxy_set(self, message):
        # Since GATT Proxy not supported, respond with status
        gatt_proxy = self.global_states_manager.get_state("gatt_proxy").get_value()
        response = BTMesh_Model_Config_Gatt_Proxy_Status(gatt_proxy=gatt_proxy)
        return response

    def on_friend_get(self, message):
        friend = self.global_states_manager.get_state("friend").get_value()
        response = BTMesh_Model_Config_Friend_Status(friend=friend)
        return response

    def on_friend_set(self, message):
        # friend feature not supported
        friend = self.global_states_manager.get_state("friend").get_value()
        response = BTMesh_Model_Config_Friend_Status(friend=friend)
        return response

    def on_relay_get(self, message):
        # relay not supported yet
        relay_composite = self.global_states_manager.get_state("relay_retransmit")
        relay_retransmit_count = relay_composite.get_sub_state(
            "relay_retransmit_count"
        ).get_value()
        relay_retransmit_interval_steps = relay_composite.get_sub_state(
            "relay_retransmit_interval_steps"
        ).get_value()
        relay = self.global_states_manager.get_state("relay").get_value()
        response = BTMesh_Model_Config_Relay_Status(
            relay=relay,
            relay_retransmit_count=relay_retransmit_count,
            relay_retransmit_interval_step=relay_retransmit_interval_steps,
        )
        return response

    def on_relay_set(self, message):
        # relay not supported yet
        relay_composite = self.global_states_manager.get_state("relay_retransmit")
        relay_retransmit_count = relay_composite.get_sub_state(
            "relay_retransmit_count"
        ).get_value()
        relay_retransmit_interval_steps = relay_composite.get_sub_state(
            "relay_retransmit_interval_steps"
        ).get_value()
        relay = self.global_states_manager.get_state("relay").get_value()
        response = BTMesh_Model_Config_Relay_Status(
            relay=relay,
            relay_retransmit_count=relay_retransmit_count,
            relay_retransmit_interval_step=relay_retransmit_interval_steps,
        )
        return response

    def on_model_publication_get(self, message):
        # All verifications (table 4.313) are checked in Access Layer
        element_addr = message.element_addr
        model_identifier = message.model_identifier
        status = 0
        model_composite = self.global_states_manager.get_state(
            "model_publication", model_id=model_identifier, element_addr=element_addr
        )
        if model_composite is None:
            status = 0x02

        publish_addr = model_composite.get_sub_state(
            "model_publication_publish_address"
        ).get_value()

        if get_address_type(publish_addr) == UNASSIGNED_ADDR_TYPE:
            credential_flag = 0
            app_key_index = 0
            publish_ttl = 0
            publish_period = 0
            publish_retransmit_interval_steps = 0
            publish_retransmit_count = 0
        else:
            credential_flag = model_composite.get_sub_state(
                "model_publication_publish_friendship_credential_flag"
            ).get_value()
            app_key_index = model_composite.get_sub_state(
                "model_publication_publish_app_key_index"
            ).get_value()
            publish_ttl = model_composite.get_sub_state(
                "model_publication_publish_ttl"
            ).get_value()
            publish_period = model_composite.get_sub_state(
                "model_publication_publish_period"
            ).get_publish_period()
            publish_retransmit_count = model_composite.get_sub_state(
                "model_publication_publish_retransmit_count"
            ).get_value()
            publish_retransmit_interval_steps = model_composite.get_sub_state(
                "model_publication_publish_retransmit_interval_steps"
            ).get_value()

        response = BTMesh_Model_Config_Publication_Status(
            status=status,
            element_addr=element_addr,
            publish_addr=publish_addr,
            credential_flag=credential_flag,
            app_key_index=app_key_index,
            publish_ttl=publish_ttl,
            publish_period=publish_period,
            publish_retransmit_interval_steps=publish_retransmit_interval_steps,
            publish_retransmit_count=publish_retransmit_count,
            model_identifier=model_identifier,
        )

        return response

    def on_model_publication_set(self, message):
        element_addr = message.element_addr
        model_identifier = message.model_identifier
        model_composite = self.global_states_manager.get_state(
            "model_publication", model_id=model_identifier, element_addr=element_addr
        )
        status = 0

        if model_composite is None:
            status = 0x02
            credential_flag = 0
            app_key_index = 0
            publish_ttl = 0
            publish_period = 0
            publish_retransmit_interval_steps = 0
            publish_retransmit_count = 0

        publish_addr = message.publish_addr
        if get_address_type(publish_addr) == UNASSIGNED_ADDR_TYPE:
            model_composite.get_sub_state(
                "model_publication_publish_address"
            ).set_value(message.publish_addr)
            credential_flag = 0
            app_key_index = 0
            publish_ttl = 0
            publish_period = 0
            publish_retransmit_interval_steps = 0
            publish_retransmit_count = 0
        else:
            model_composite.get_sub_state(
                "model_publication_publish_address"
            ).set_value(bytes.fromhex(hex(message.publish_addr)[2:]))
            model_composite.get_sub_state(
                "model_publication_publish_friendship_credential_flag"
            ).set_value(message.credential_flag)
            model_composite.get_sub_state(
                "model_publication_publish_app_key_index"
            ).set_value(message.app_key_index)
            model_composite.get_sub_state("model_publication_publish_ttl").set_value(
                message.publish_ttl
            )
            model_composite.get_sub_state("model_publication_publish_period").set_value(
                field_name="nb_of_steps", value=message.publish_period
            )
            model_composite.get_sub_state(
                "model_publication_publish_retransmit_count"
            ).set_value(message.publish_retransmit_count)
            model_composite.get_sub_state(
                "model_publication_publish_retransmit_interval_steps"
            ).set(message.publish_retransmit_interval_steps)
            credential_flag = model_composite.get_sub_state(
                "model_publication_publish_friendship_credential_flag"
            ).get_value()
            app_key_index = model_composite.get_sub_state(
                "model_publication_publish_ttl"
            ).get_value()
            publish_ttl = model_composite.get_sub_state(
                "model_publication_publish_ttl"
            ).get_value()
            publish_period = model_composite.get_sub_state(
                "model_publication_publish_period"
            ).get_publish_period()
            publish_retransmit_interval_steps = model_composite.get_sub_state(
                "model_publication_publish_retransmit_interval_steps"
            ).get_value()
            publish_retransmit_count = model_composite.get_sub_state(
                "model_publication_publish_retransmit_count"
            ).get_value()

        response = BTMesh_Model_Config_Publication_Status(
            status=status,
            element_addr=message.element_addr,
            publish_addr=publish_addr,
            credential_flag=credential_flag,
            app_key_index=app_key_index,
            publish_ttl=publish_ttl,
            publish_period=publish_period,
            publish_retransmit_interval_steps=publish_retransmit_interval_steps,
            publish_retransmit_count=publish_retransmit_count,
            model_identifier=message.model_identifier,
        )
        return response

    def on_model_subscription_add(self, message):
        # checks for element_addr performed on Access layer
        element_addr = message.element_addr
        model_identifier = message.model_identifier
        sub_grp_addr_list = self.global_states_manager.get_state(
            "subscription_list",
            element_addr=element_addr,
            model_identifier=model_identifier,
        ).get_value("group_addrs")

        addr = bytes.fromhex(hex(message.address))
        if addr not in sub_grp_addr_list:
            sub_grp_addr_list.append(bytes.fromhex(hex(addr)))

        response = BTMesh_Model_Config_Subscription_Status(
            status=0,
            element_addr=message.element_addr,
            address=message.address,
            model_identifier=message.model_identifier,
        )
        return response

    def on_model_subscription_virtual_address_add(self, message):
        # checks performeed on Access Layer
        element_addr = message.element_addr
        model_identifier = message.model_identifier

        sub_label_uuid_list = self.global_states_manager.get_state(
            "subscription_list", element_addr=element_addr, model_id=model_identifier
        ).get_value("label_uuids")
        if message.label not in sub_label_uuid_list:
            sub_label_uuid_list.append(message.label)

        virtual_addr = compute_virtual_addr_from_label_uuid(message.label)
        response = BTMesh_Model_Config_Subscription_Status(
            status=0,
            element_addr=message.element_addr,
            address=virtual_addr,
            model_identifier=message.model_identifier,
        )
        return response

    def on_model_subscription_delete(self, message):
        # checks performed on Acces layer
        element_addr = message.element_addr
        model_identifier = message.model_identifier

        sub_grp_addr_list = self.global_states_manager.get_state(
            "subscription_list", element_addr=element_addr, model_id=model_identifier
        ).get_value("group_addrs")

        addr = bytes.fromhex(hex(message.address))
        if addr not in sub_grp_addr_list:
            sub_grp_addr_list.remove(addr)

        response = BTMesh_Model_Config_Subscription_Status(
            status=0,
            element_addr=message.element_addr,
            address=message.address,
            model_identifier=message.model_identifier,
        )
        return response

    def on_model_subscription_virtual_address_delete(self, message):
        element_addr = message.element_addr
        model_identifier = message.model_identifier

        sub_label_uuid_list = self.global_states_manager.get_state(
            "subscription_list", element_addr=element_addr, model_id=model_identifier
        ).get_value("label_uuids")

        if message.label not in sub_label_uuid_list:
            sub_label_uuid_list.remove(message.label)

        virtual_addr = compute_virtual_addr_from_label_uuid(message.label)
        response = BTMesh_Model_Config_Subscription_Status(
            status=0,
            element_addr=message.element_addr,
            address=virtual_addr,
            model_identifier=message.model_identifier,
        )
        return response

    def on_model_subscription_overwrite(self, message):
        element_addr = message.element_addr
        model_identifier = message.model_identifier
        addr = bytes.fromhex(hex(message.address))

        state = self.global_states_manager.get_state(
            "subscription_list", element_addr=element_addr, model_id=model_identifier
        )
        state.set_value(field_name="label_uuids", value=[])
        state.set_value(field_name="group_addrs", value=[addr])
        response = BTMesh_Model_Config_Subscription_Status(
            status=0,
            element_addr=message.element_addr,
            address=message.address,
            model_identifier=message.model_identifier,
        )
        return response

    def on_model_subscription_virtual_overwrite(self, message):
        element_addr = message.element_addr
        model_identifier = message.model_identifier

        state = self.global_states_manager.get_state(
            "subscription_list", element_addr=element_addr, model_id=model_identifier
        )
        state.set_value(field_name="label_uuids", value=[message.label])
        state.set_value(field_name="group_addrs", value=[])

        virtual_addr = compute_virtual_addr_from_label_uuid(message.label)
        response = BTMesh_Model_Config_Subscription_Status(
            status=0,
            element_addr=message.element_addr,
            address=virtual_addr,
            model_identifier=message.model_identifier,
        )
        return response

    def on_model_subscription_delete_all(self, message):
        element_addr = message.element_addr
        model_identifier = message.model_identifier

        state = self.global_states_manager.get_state(
            "subscription_list", element_addr=element_addr, model_id=model_identifier
        )
        state.set_value(field_name="label_uuids", value=[])
        state.set_value(field_name="group_addrs", value=[])
        response = BTMesh_Model_Config_Subscription_Status(
            status=0,
            element_addr=message.element_addr,
            address=b"\x00\x00",
            model_identifier=message.model_identifier,
        )
        return response

    def on_model_subscription_sig_get(self, message):
        # checks performed on Access Layer
        element_addr = message.element_addr
        model_identifier = message.model_identifier

        state = self.global_states_manager.get_state(
            "subscription_list", element_addr=element_addr, model_id=model_identifier
        )
        group_addresses = state.get_value("group_addrs")
        label_uuids = state.get_value("label_uuids")

        virtual_addresses = []

        for label_uuid in label_uuids:
            virtual_addresses.append(compute_virtual_addr_from_label_uuid(label_uuid))

        for i in range(len(group_addresses)):
            group_addresses[i] = bytes.fromhex(hex(group_addresses[i]))

        addresses = b"".join(group_addresses) + b"".join(virtual_addresses)
        response = BTMesh_Model_Config_SIG_Model_Subscription_List(
            status=0,
            element_addr=message.element_addr,
            model_identifier=message.model_identifier,
            addresses=addresses,
        )
        return response

    def on_net_key_add(self, message):
        net_key_index = message.net_key_index
        net_key = message.net_key
        net_key_list = self.global_states_manager.get_state("net_key_list")
        stored_net_key = net_key_list.get_value(net_key_index)

        if stored_net_key is not None and stored_net_key.net_key != net_key:
            response = BTMesh_Model_Config_Net_Key_Status(
                status=0x06, net_key_index=net_key_index
            )
        else:
            net_key_crypto_manager = NetworkLayerCryptoManager(
                key_index=net_key_index, net_key=net_key
            )
            net_key_list.set_value(
                field_name=net_key_index, value=net_key_crypto_manager
            )
            response = BTMesh_Model_Config_Net_Key_Status(
                status=0, net_key_index=net_key_index
            )
        return response

    def on_net_key_update(self, message):
        net_key_index = message.net_key_index
        net_key = message.net_key

        net_key_list = self.global_states_manager.get_state("net_key_list")
        stored_net_key = net_key_list.get_value(net_key_index)

        if stored_net_key is None:
            response = BTMesh_Model_Config_Net_Key_Status(
                status=0x04, net_key_index=net_key_index
            )
        else:
            net_key_crypto_manager = NetworkLayerCryptoManager(
                key_index=net_key_index, net_key=net_key
            )
            net_key_list.set_value(
                field_name=net_key_index, value=net_key_crypto_manager
            )
            response = BTMesh_Model_Config_Net_Key_Status(
                status=0, net_key_index=net_key_index
            )
        return response

    def __disable_model_publication(
        self, app_key_index, model_id=None, element_addr=None
    ):
        """
        Disable the publication for models that use a deleted app_key_index
        If model_id specified, only disables publication for the model if app_key_index is used for publication of this Model (and need also element_addr)
        """
        pub_states = self.global_states_manager.get_all_state("model_publication")
        if pub_states is not None:
            for state in pub_states:
                state_key_index = state.get_sub_state(
                    "model_publication_publish_app_key_index"
                ).get_value()
                if state_key_index == app_key_index and (
                    model_id is None or model_id == state.model_id
                ):
                    state.get_sub_state("model_publication_publish_address").set_value(
                        b"\x00\x00"
                    )

    def __disable_heartbeat_publication(self, net_key_index):
        """
        Disable the Heartbeat publication that use a deleted NetKey
        """
        hp_states = self.global_states_manager.get_all_states("heartbeat_publication")
        if hp_states is not None:
            for state in hp_states:
                if (
                    state.get_sub_state(
                        "heartbeat_publication_net_key_index"
                    ).get_value()
                    == net_key_index
                ):
                    state.get_sub_state("heartbeat_publication_destination").set_value(
                        b"\x00\x00"
                    )

    # TODO: ADD Mesh Proxy, Directed Forwarding and Subnet Bridging states update on delete ...
    def on_net_key_delete(self, message):
        net_key_index = message.net_key_index
        stored_net_key = self.global_states_manager.get_state("net_key_list").remove(
            net_key_index
        )

        if stored_net_key is not None:
            # disable heartbeat publication if bound to this NetKey
            self.__disable_heartbeat_publication(net_key_index)

            # remove all appKey bound to this netkey
            for app_key_index in stored_net_key.app_key_indexes:
                self.global_states_manager.get_state("app_key_list").remove(
                    app_key_index
                )

                # disable publication for app_key that are deleted
                self.__disable_model_publication(app_key_index)

        response = BTMesh_Model_Config_Net_Key_Status(
            status=0, net_key_index=net_key_index
        )
        return response

    def on_net_key_get(self, message):
        net_keys = self.global_states_manager.get_state("net_key_list").get_all_values()
        # remove default value because useless
        net_keys.pop("default")

        # For each index, i.e dict key, we get the value
        net_key_indexes = net_keys.keys()

        # use the function in utils to get the correct formatting for the scapy packet
        net_key_indexes = key_indexes_to_packet_encoding(net_key_indexes)

        response = BTMesh_Model_Config_Net_Key_List(net_key_indexes=net_key_indexes)
        return response

    def on_app_key_add(self, message):
        app_key_index = message.app_key_index
        net_key_index = message.net_key_index
        stored_app_key = self.global_states_manager.get_state("app_key_list").get_value(
            app_key_index
        )
        stored_net_key = self.global_states_manager.get_state("net_key_list").get_value(
            net_key_index
        )
        if stored_net_key is None:
            status = 0x03
        elif stored_app_key is not None and stored_app_key.app_key != message.app_key:
            status = 0x06
        elif (
            stored_app_key is not None and stored_app_key.net_key_index != net_key_index
        ):
            status = 0x4
        else:
            app_key_crypto_manager = UpperTransportLayerAppKeyCryptoManager(
                app_key=message.app_key, net_key_index=net_key_index
            )
            self.global_states_manager.get_state("app_key_list").set_value(
                field_name=app_key_index, value=app_key_crypto_manager
            )

            stored_net_key.add_app_key_index(app_key_index)
            status = 0

        response = BTMesh_Model_Config_App_Key_Status(
            status=status, net_key_index=net_key_index, app_key_index=app_key_index
        )
        return response

    def on_app_key_update(self, message):
        app_key_index = message.app_key_index
        net_key_index = message.net_key_index
        stored_app_key = self.global_states_manager.get_state("app_key_list").get_value(
            app_key_index
        )
        stored_net_key = self.global_states_manager.get_state("net_key_list").get_value(
            net_key_index
        )
        if stored_net_key is None:
            status = 0x03
        elif (
            stored_app_key is not None and stored_app_key.net_key_index != net_key_index
        ):
            status = 0x11
        else:
            app_key_crypto_manager = UpperTransportLayerAppKeyCryptoManager(
                app_key=message.app_key, net_key_index=net_key_index
            )
            self.global_states_manager.get_state("app_key_list").set_value(
                field_name=app_key_index, value=app_key_crypto_manager
            )
            status = 0

        response = BTMesh_Model_Config_App_Key_Status(
            status=status, net_key_index=net_key_index, app_key_index=app_key_index
        )
        return response

    def on_app_key_delete(self, message):
        # need to update model publication states ....
        app_key_index = message.app_key_index
        net_key_index = message.net_key_index
        stored_app_key = self.global_states_manager.get_state("app_key_list").get_value(
            app_key_index
        )
        stored_net_key = self.global_states_manager.get_state("net_key_list").get_value(
            net_key_index
        )
        status = 0
        if stored_net_key is None:
            status = 0x03

        if stored_app_key is not None and stored_net_key is not None:
            # disable publication for models that use this app key
            self.__disable_model_publication(app_key_index)

            stored_net_key.app_key_indexes.remove(app_key_index)

        response = BTMesh_Model_Config_App_Key_Status(
            status=status, app_key_index=app_key_index, net_key_index=net_key_index
        )
        return response

    def on_app_key_get(self, message):
        net_key_index = message.net_key_index
        stored_net_key = self.global_states_manager.get_state("net_key_list").get_value(
            net_key_index
        )
        if stored_net_key is None:
            status = 0x03
            app_key_indexes = []
        else:
            status = 0
            app_key_indexes = stored_net_key.app_key_indexes.copy()
            app_key_indexes = key_indexes_to_packet_encoding(
                app_key_indexes
            )  # encode the app_key list to packet format
        response = BTMesh_Model_Config_App_Key_List(
            status=status, net_key_index=net_key_index, app_key_indexes=app_key_indexes
        )
        return response

    def on_model_to_app_key_bind(self, message):
        # checks for invalid model, invalid addr are checked on access layer
        model_id = message.model_identifier
        app_key_index = message.app_key_index
        stored_app_key = self.global_states_manager.get_state("app_key_list").get_value(
            app_key_index
        )
        if stored_app_key is None:
            status = 0x03

        else:
            status = 0
            app_key_list = self.global_states_manager.get_state(
                "model_to_app_key_list"
            ).get_value(model_id)
            if app_key_list is None:
                self.global_states_manager.get_state("model_to_app_key_list").set_value(
                    field_name=model_id, value=[app_key_index]
                )
            elif app_key_index not in app_key_list:
                app_key_list.append(app_key_index)

        response = BTMesh_Model_Config_Model_App_Status(
            status=status,
            element_addr=message.element_addr,
            app_key_index=app_key_index,
            model_identifier=model_id,
        )
        return response

    def on_model_to_app_key_unbind(self, message):
        # checks for invalid model, invalid addr are checked on access layer
        model_id = message.model_identifier
        app_key_index = message.app_key_index
        stored_app_key = self.global_states_manager.get_state("app_key_list").get_value(
            app_key_index
        )
        if stored_app_key is None:
            status = 0x03
        else:
            # disable model publication for model that use this key
            self.__disable_model_publication(app_key_index, model_id)

            app_key_list = self.global_states_manager.get_state(
                "model_to_app_key_list"
            ).get_value(model_id)
            if app_key_index in app_key_index:
                app_key_list.remove(app_key_index)
        response = BTMesh_Model_Config_Model_App_Status(
            status=status,
            element_addr=message.element_addr,
            app_key_index=app_key_index,
            model_identifier=model_id,
        )
        return response

    def on_sig_model_to_app_key_get(self, message):
        # checks for invalid model, invalid addr in access layer
        model_id = message.model_identifier
        app_key_list = self.global_states_manager.get_state(
            "model_to_app_key_list"
        ).get_value(model_id)

        formated_index_list = key_indexes_to_packet_encoding(app_key_list)
        response = BTMesh_Model_Config_SIG_Model_App_List(
            status=0,
            element_addr=message.element_addr,
            model_identifier=model_id,
            app_key_indexes=formated_index_list,
        )
        return response

    def on_vendor_model_to_app_key_get(self, message):
        # checks for invalid model, invalid addr in access layer
        model_id = message.model_identifier
        app_key_list = self.global_states_manager.get_state(
            "model_to_app_key_list"
        ).get_value(model_id)

        formated_index_list = key_indexes_to_packet_encoding(app_key_list)
        response = BTMesh_Model_Config_Vendor_Model_App_List(
            status=0,
            element_addr=message.element_addr,
            model_identifier=model_id,
            app_key_indexes=formated_index_list,
        )
        return response

    def on_node_identity_get(self, message):
        net_key_index = message.net_key_index
        stored_net_key = self.global_states_manager.get_state("net_key_list").get_value(
            net_key_index
        )
        if stored_net_key is None:
            status = 0x04
            node_identity = 0
        else:
            status = 0
            node_identity = self.global_states_manager.get_state(
                "node_identity", net_key_index=net_key_index
            ).get_value()

        response = BTMesh_Model_Config_Node_Identity_Status(
            status=status, net_key_index=net_key_index, identity=node_identity
        )
        return response

    def on_node_identity_set(self, message):
        net_key_index = message.net_key_index
        stored_net_key = self.global_states_manager.get_state("net_key_list").get_value(
            net_key_index
        )
        if stored_net_key is None:
            status = 0x04
            node_identity = 0
        else:
            status = 0
            node_identity = message.identity
            self.global_states_manager.get_state(
                "node_identity", net_key_index=net_key_index
            ).set_value(node_identity)

        response = BTMesh_Model_Config_Node_Identity_Status(
            status=status, net_key_index=net_key_index, identity=node_identity
        )
        return response

    def on_node_reset(self, message):
        # Not implemented yet
        response = BTMesh_Model_Config_Node_Reset_Status()
        return response

    def on_key_refresh_phase_get(self, message):
        net_key_index = message.net_key_index
        stored_net_key = self.global_states_manager.get_state("net_key_list").get_value(
            net_key_index
        )
        if stored_net_key is None:
            status = 0x04
            phase = 0
        else:
            status = 0
            phase = self.global_states_manager.get_state(
                "key_refresh_list", net_key_index=net_key_index
            ).get_value()

        response = BTMesh_Model_Config_Key_Refresh_Phase_Status(
            status=status, net_key_index=net_key_index, phase=phase
        )
        return response

    def on_key_refresh_phase_set(self, message):
        net_key_index = message.net_key_index
        stored_net_key = self.global_states_manager.get_state("net_key_list").get_value(
            net_key_index
        )
        if stored_net_key is None:
            status = 0x04
            phase = 0
        else:
            status = 0
            phase = message.transition
            self.global_states_manager.get_state(
                "key_refresh_list", net_key_index=net_key_index
            ).set_value(phase)

        response = BTMesh_Model_Config_Key_Refresh_Phase_Status(
            status=status, net_key_index=net_key_index, phase=phase
        )
        return response

    def on_heartbeat_publication_get(self, message):
        hb_pub_state = self.global_states_manager.get_state("heartbeat_publication")
        dest = hb_pub_state.get_sub_state(
            "heartbeat_publication_destination"
        ).get_value()

        if get_address_type(dest) == UNASSIGNED_ADDR_TYPE:
            count_log = 0
            period_log = 0
            ttl = 0
            features = 0
            net_key_index = 0
        else:
            count_log = hb_pub_state.get_sub_state(
                "heartbeat_publication_count"
            ).get_value()
            period_log = hb_pub_state.get_sub_state(
                "heartbeat_publication_period_log"
            ).get_value()
            ttl = hb_pub_state.get_sub_state("heartbeat_publication_ttl").get_value()
            features = hb_pub_state.get_sub_state(
                "heartbeat_publication_features"
            ).get_value()
            net_key_index = hb_pub_state.get_sub_state(
                "heartbeat_publication_net_key_index"
            ).get_value()

        response = BTMesh_Config_Model_Heartbeat_Publication_Status(
            status=0,
            destination=dest,
            count_log=count_log,
            period_log=period_log,
            ttl=ttl,
            features=features,
            net_key_index=net_key_index,
        )
        return response

    def on_heartbeat_publication_set(self, message):
        net_key_index = message.net_key_index
        stored_net_key = self.global_states_manager.get_state("net_key_list").get_value(
            net_key_index
        )

        destination = message.destination
        count_log = message.count_log
        period_log = message.period_log
        ttl = message.ttl
        features = message.features
        net_key_index = message.net_key_index

        hb_pub_state = self.global_states_manager.get_state("heartbeat_publication")

        if stored_net_key is None:
            status = 0x04
        else:
            status = 0

            hb_pub_state.get_sub_state("heartbeat_publication_destination").set_value(
                destination
            )

            hb_pub_state.get_sub_state("heartbeat_publication_count").set_value(
                count_log
            )
            hb_pub_state.get_sub_state("heartbeat_publication_period_log").set_value(
                period_log
            )
            hb_pub_state.get_sub_state("heartbeat_publication_ttl").set_value(ttl)
            hb_pub_state.get_sub_state("heartbeat_publication_features").set_value(
                features
            )
            hb_pub_state.get_sub_state("heartbeat_publication_net_key_index").set_value(
                net_key_index
            )

        response = BTMesh_Config_Model_Heartbeat_Publication_Status(
            status=status,
            destination=destination,
            count_log=count_log,
            period_log=period_log,
            ttl=ttl,
            features=features,
            net_key_index=net_key_index,
        )
        return response

    def on_heartbeat_subscription_get(self, message):
        hb_sub_state = self.global_states_manager.get_state("heartbeat_subscription")
        status = 0
        source = hb_sub_state.get_sub_state("heartbeat_subscription_source").get_value()
        destination = hb_sub_state.get_sub_state(
            "heartbeat_subscription_destination"
        ).get_value()
        count_log = hb_sub_state.get_sub_state(
            "heartbeat_subscription_count"
        ).get_value()
        period_log = hb_sub_state.get_sub_state(
            "heartbeat_subscription_period"
        ).get_value()
        min_hops = hb_sub_state.get_sub_state(
            "heartbeat_subscription_min_hops"
        ).get_value()
        max_hops = hb_sub_state.get_sub_state(
            "heartbeat_subscription_max_hops"
        ).get_value()

        response = BTMesh_Config_Model_Heartbeat_Subscription_Status(
            status=status,
            source=source,
            destination=destination,
            count_log=count_log,
            period_log=period_log,
            min_hops=min_hops,
            max_hops=max_hops,
        )
        return response

    def on_heartbeat_subscription_set(self, message):
        source = message.source
        destination = message.destination
        period_log = message.period_log

        hb_sub_state = self.global_states_manager.get_state("heartbeat_subscription")

        if (
            get_address_type(source) == UNASSIGNED_ADDR_TYPE
            or get_address_type(destination) == UNASSIGNED_ADDR_TYPE
            or period_log == 0
        ):
            # disable process of heartbeat messages
            hb_sub_state.get_sub_state("heartbeat_subscription_destination").set_value(
                b"\x00\x00"
            )
            hb_sub_state.get_sub_state("heartbeat_subscription_source").set_value(
                b"\x00\x00"
            )
            hb_sub_state.get_sub_state("heartbeat_subscription_period").set_value(0x00)

            status = 0
            source = 0
            destination = 0
            period_log = 0
            min_hops = hb_sub_state.get_sub_state(
                "heartbeat_subscription_min_hops"
            ).get_value()
            max_hops = hb_sub_state.get_sub_state(
                "heartbeat_subscription_max_hops"
            ).get_value()
            count_log = hb_sub_state.get_sub_state(
                "heartbeat_subscription_count"
            ).get_value()

        elif (
            get_address_type(source) == UNICAST_ADDR_TYPE
            and (
                get_address_type(destination) == UNICAST_ADDR_TYPE
                or get_address_type(destination) == GROUP_ADDR_TYPE
            )
            and period_log != 0
        ):
            hb_sub_state.get_sub_state("heartbeat_subscription_destination").set_value(
                source
            )
            hb_sub_state.get_sub_state("heartbeat_subscription_source").set_value(
                destination
            )
            hb_sub_state.get_sub_state("heartbeat_subscription_period").set_value(
                period_log
            )
            hb_sub_state.get_sub_state("heartbeat_subscription_min_hops").set_value(
                0x7F
            )
            hb_sub_state.get_sub_state("heartbeat_subscription_max_hops").set_value(
                0x00
            )
            hb_sub_state.get_sub_state("heartbeat_subscription_count").set_value(0x00)

            status = 0
            min_hops = hb_sub_state.get_sub_state(
                "heartbeat_subscription_min_hops"
            ).get_value()
            max_hops = hb_sub_state.get_sub_state(
                "heartbeat_subscription_max_hops"
            ).get_value()
            count_log = hb_sub_state.get_sub_state(
                "heartbeat_subscription_count"
            ).get_value()

        response = BTMesh_Config_Model_Heartbeat_Subscription_Status(
            status=status,
            source=source,
            destination=destination,
            count_log=count_log,
            period_log=period_log,
            min_hops=min_hops,
            max_hops=max_hops,
        )
        return response

    def on_lpn_poll_timeout_get(self, message):
        lpn_addr = message.lpn_addr

        timeout = self.global_states_manager.get_state("poll_timeout_list").get_value(
            lpn_addr
        )
        response = BTMesh_Model_Config_Low_Power_Node_Poll_Timemout_Status(
            lpn_addr=lpn_addr, poll_timeout=timeout
        )
        return response

    def on_network_transmit_get(self, message):
        state = self.global_states_manager.get_state("network_transmit")
        count = state.get_sub_state("network_transmit_count").get_value()
        interval_steps = state.get_sub_state(
            "network_transmit_interval_steps"
        ).get_value()

        response = BTMesh_Model_Config_Network_Transmit_Status(
            network_transmit_interval_steps=interval_steps,
            network_transmit_count=count,
        )
        return response

    def on_network_transmit_set(self, message):
        state = self.global_states_manager.get_state("network_transmit")
        count = message.network_transmit_count
        interval_steps = message.network_transmit_interval_steps

        state.get_sub_state("network_transmit_count").set_value(count)
        state.get_sub_state("network_transmit_interval_steps").set_value(interval_steps)
        response = BTMesh_Model_Config_Network_Transmit_Status(
            network_transmit_interval_steps=interval_steps,
            network_transmit_count=count,
        )

        return response
