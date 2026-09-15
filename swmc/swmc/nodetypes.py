"""Stormworks microprocessor component type tables.

AUTO-GENERATED from stormworks64.exe by reverse engineering; do not edit by hand.

Extracted from:

    Stormworks: Build and Rescue v1.15.23
    stormworks64.exe, 13,944,320 bytes
    sha256 f9206d85c82f4d02fd0ac391781d19c5c68394a9ffc48accca0e1f5966db8699

The game embeds Lua 5.3. If your build differs, re-check these tables before
trusting them: type ids are stable in practice, but a new component type would
be appended and the field schema can change.

Sources inside the binary (imagebase 0x140000000):
  * component definition table   qword_140D1B088, built by sub_140367330
    60 entries x 128 bytes; entry = table + (type << 7)
  * <c type="N"> -> object factory      sub_14038BD80
  * <c type="N"> bridge factory          sub_14038CA00
  * per-type XML serializer               vtable slot 5 of each component class
  * mesh name by type                     sub_140370140
  * category name by id                   sub_14036FFF0
"""

from __future__ import annotations

# Hand-maintained additions to this generated file: this import, and the
# SOURCE dict below recording which build the tables were read out of.
from typing import Dict, List, Optional, Tuple, Union

from .errors import UnknownTypeError

#: The build these tables were read out of.
SOURCE = {
    "game": "Stormworks: Build and Rescue",
    "game_version": "v1.15.23",
    "binary": "stormworks64.exe",
    "size_bytes": 13944320,
    "sha256": "f9206d85c82f4d02fd0ac391781d19c5c68394a9ffc48accca0e1f5966db8699",
    "imagebase": 0x140000000,
    "lua_version": "5.3",
}

CATEGORY = {0: "arithmetic", 1: "logical", 2: "control", 3: "composite", 4: "property"}

# Logic-node data types. The engine enum has 9 slots; only these are reachable
# from microprocessor components.
DATA_TYPE = {0: "on/off", 1: "number", 5: "composite", 6: "video", 7: "audio"}

#: One-letter codes for compact listings.
DATA_TYPE_SHORT = {0: "b", 1: "n", 5: "c", 6: "v", 7: "a"}

#: How each XML field of a component is encoded.
#:   link       -> child element <name component_id="ID" [id="OUT_INDEX"]/>
#:   attr_str   -> attribute on <object>, raw string
#:   attr_int   -> attribute on <object>, integer
#:   attr_float -> attribute on <object>, float
#:   prop_num   -> child element <name text="EXPR" value="FLOAT"/>
#:   state_out  -> runtime output state, only written in <component_states>
#:   state      -> runtime internal state, only written in <component_states>
FIELD_KINDS = ("link", "attr_str", "attr_int", "attr_float", "prop_num", "state_out", "state")

#: Field kinds that describe the saved design (as opposed to runtime state).
DESIGN_KINDS = ("link", "attr_str", "attr_int", "attr_float", "prop_num")


class ComponentType:
    """Static description of one <c type="N"> component."""

    __slots__ = ("type_id", "name", "cls", "category", "mesh", "description",
                 "inputs", "outputs", "fields", "variadic_inputs")

    def __init__(self, type_id: int, name: str, cls: str, category: str,
                 mesh: Optional[str], description: str,
                 inputs: "List[Tuple[str, int]]",
                 outputs: "List[Tuple[str, int]]",
                 fields: "List[Tuple[str, str]]",
                 variadic_inputs: int = 0) -> None:
        self.type_id = type_id
        self.name = name
        self.cls = cls
        self.category = category
        self.mesh = mesh
        self.description = description
        self.inputs = inputs            # [(label, data_type)]
        self.outputs = outputs          # [(label, data_type)]
        self.fields = fields            # [(field_name, kind)]
        self.variadic_inputs = variadic_inputs  # >0 for the 32-channel composite writers

    @property
    def link_fields(self) -> "List[str]":
        """XML names of the input-link child elements, in serializer order."""
        out = [f for f, k in self.fields if k == "link"]
        if self.variadic_inputs:
            out = [f for f in out if f != "in%u"]
            base = [f for f in out if f in ("inc",)]
            rest = [f for f in out if f not in ("inc",)]
            return base + ["in%d" % i for i in range(1, self.variadic_inputs + 1)] + rest
        return out

    @property
    def design_fields(self) -> "List[Tuple[str, str]]":
        """Fields that describe the saved design, excluding runtime state."""
        return [(f, k) for f, k in self.fields if k in DESIGN_KINDS]

    def field_kind(self, name: str) -> Optional[str]:
        """How one field is stored -- link, attr_str, prop_num, ... -- or None."""
        for f, k in self.fields:
            if f == name:
                return k
        if self.variadic_inputs and name.startswith("in") and name[2:].isdigit():
            if 1 <= int(name[2:]) <= self.variadic_inputs:
                return "link"
        return None

    def __repr__(self) -> str:
        return "<ComponentType %d %s>" % (self.type_id, self.name)


COMPONENT_TYPES = {
    0: ComponentType(
        0, 'NOT', 'c_microprocessor_component_not',
        'logical', 'mp_not',
        'Outputs the logical NOT of its input signal.',
        [('A', 0)],
        [('NOT A', 0)],
        [('in1', 'link'), ('out1', 'state_out')],
        0),
    1: ComponentType(
        1, 'AND', 'c_microprocessor_component_and',
        'logical', 'mp_and',
        'Outputs the logical AND of its two input signals.',
        [('A', 0), ('B', 0)],
        [('A AND B', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out')],
        0),
    2: ComponentType(
        2, 'OR', 'c_microprocessor_component_or',
        'logical', 'mp_or',
        'Outputs the logical OR of its two input signals.',
        [('A', 0), ('B', 0)],
        [('A OR B', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out')],
        0),
    3: ComponentType(
        3, 'XOR', 'c_microprocessor_component_xor',
        'logical', 'mp_xor',
        'Outputs the logical XOR of its two input signals.',
        [('A', 0), ('B', 0)],
        [('A XOR B', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out')],
        0),
    4: ComponentType(
        4, 'NAND', 'c_microprocessor_component_nand',
        'logical', 'mp_nand',
        'Outputs the logical NAND of its two input signals.',
        [('A', 0), ('B', 0)],
        [('A NAND B', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out')],
        0),
    5: ComponentType(
        5, 'NOR', 'c_microprocessor_component_nor',
        'logical', 'mp_nor',
        'Outputs the logical NOR of its two input signals.',
        [('A', 0), ('B', 0)],
        [('A NOR B', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out')],
        0),
    6: ComponentType(
        6, 'Add', 'c_microprocessor_component_add',
        'arithmetic', 'mp_add',
        'Adds the two input values together and outputs the result.',
        [('A', 1), ('B', 1)],
        [('A + B', 1)],
        [('in1', 'link'), ('in2', 'link')],
        0),
    7: ComponentType(
        7, 'Subtract', 'c_microprocessor_component_subtract',
        'arithmetic', 'mp_subtract',
        'Subtracts the second input from the first and outputs the result.',
        [('A', 1), ('B', 1)],
        [('A - B', 1)],
        [('in1', 'link'), ('in2', 'link')],
        0),
    8: ComponentType(
        8, 'Multiply', 'c_microprocessor_component_multiply',
        'arithmetic', 'mp_multiply',
        'Multiplies the two input values and outputs the result.',
        [('A', 1), ('B', 1)],
        [('A x B', 1)],
        [('in1', 'link'), ('in2', 'link')],
        0),
    9: ComponentType(
        9, 'Divide', 'c_microprocessor_component_divide',
        'arithmetic', 'mp_divide',
        'Divides the first input by the second and outputs the result.',
        [('A', 1), ('B', 1)],
        [('A / B', 1), ('Divide By Zero', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out2', 'state_out')],
        0),
    10: ComponentType(
        10, 'f(x, y, z)', 'c_microprocessor_component_function',
        'arithmetic', 'mp_function',
        'Evaluates a mathematical expression with up to 3 input variables and outputs the result.',
        [('x', 1), ('y', 1), ('z', 1)],
        [('f(x, y, z)', 1)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link'), ('e', 'attr_str'), ('p1', 'attr_float'), ('p2', 'attr_float'), ('p3', 'attr_float')],
        0),
    11: ComponentType(
        11, 'Clamp', 'c_microprocessor_component_clamp',
        'arithmetic', 'mp_clamp',
        'Clamps the input value between a set min and max and outputs the result.',
        [('Input Number', 1)],
        [('Clamped Input', 1)],
        [('in1', 'link'), ('min', 'prop_num'), ('max', 'prop_num')],
        0),
    12: ComponentType(
        12, 'Threshold', 'c_microprocessor_component_threshold',
        'control', 'mp_threshold',
        'Outputs an on/off signal indicating whether or not the input value is within a set threshold.',
        [('Input Number', 1)],
        [('Within Threshold', 0)],
        [('in1', 'link'), ('out1', 'state_out'), ('min', 'prop_num'), ('max', 'prop_num')],
        0),
    13: ComponentType(
        13, 'Memory Register', 'c_microprocessor_component_memory',
        'control', 'mp_memory',
        'Remembers the input value when receiving a signal to the Set node. When the Reset node receives a signal, the stor',
        [('Set', 0), ('Reset', 0), ('Number to store', 1)],
        [('Stored Number', 1)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link'), ('memory', 'attr_float'), ('r', 'prop_num')],
        0),
    14: ComponentType(
        14, 'Abs', 'c_microprocessor_component_abs',
        'arithmetic', 'mp_abs',
        'Outputs the absolute value of the input value (negative numbers become positive).',
        [('Input Number', 1)],
        [('Absolute Value', 1)],
        [('in1', 'link')],
        0),
    15: ComponentType(
        15, 'Constant Number', 'c_microprocessor_component_constant_number',
        'arithmetic', 'mp_constant_number',
        'Outputs a constant number that is set on the properties panel.',
        [],
        [('Constant Value', 1)],
        [('n', 'prop_num')],
        0),
    16: ComponentType(
        16, 'Constant On Signal', 'c_microprocessor_component_constant_bool',
        'logical', 'mp_constant_bool',
        'Outputs a constant on signal.',
        [],
        [('On Signal', 0)],
        [('out1', 'state_out')],
        0),
    17: ComponentType(
        17, 'Greater Than', 'c_microprocessor_component_greater_than',
        'control', 'mp_greater_than',
        'Outputs an on signal if the first input is greater than the second.',
        [('A', 1), ('B', 1)],
        [('A > B', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out')],
        0),
    18: ComponentType(
        18, 'Less Than', 'c_microprocessor_component_less_than',
        'control', 'mp_less_than',
        'Outputs an on signal if the first value is less than the second.',
        [('A', 1), ('B', 1)],
        [('A << B', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out')],
        0),
    19: ComponentType(
        19, 'Property Slider', 'c_microprocessor_component_property_slider',
        'property', 'mp_property_number_slider',
        "Adds a custom slider that will be seen on the microcontroller's property panel when placed on a vehicle.",
        [],
        [('Slider Value', 1)],
        [('name', 'attr_str'), ('min', 'prop_num'), ('max', 'prop_num'), ('int', 'prop_num'), ('v', 'prop_num')],
        0),
    20: ComponentType(
        20, 'Property Dropdown', 'c_microprocessor_component_property_selector',
        'property', 'mp_property_number_selector',
        "Adds a custom dropdown list that will be seen on the microcontroller's property panel when placed on a vehicle.",
        [],
        [('Selected Value', 1)],
        [('name', 'attr_str'), ('v', 'attr_float'), ('i', 'attr_int')],
        0),
    21: ComponentType(
        21, 'Numerical Junction', 'c_microprocessor_component_numerical_junction',
        'control', 'mp_numerical_junction',
        'Outputs the input number to one of the outputs depending on whether or not the Switch Signal is on. The path that ',
        [('Value To Pass Through', 1), ('Switch Signal', 0)],
        [('On Path', 1), ('Off Path', 1)],
        [('in1', 'link'), ('in2', 'link')],
        0),
    22: ComponentType(
        22, 'Numerical Switchbox', 'c_microprocessor_component_numerical_switchbox',
        'control', 'mp_numerical_switchbox',
        'Outputs the first input value when receiving an on signal, and the second when receiving an off signal.',
        [('First Value (On)', 1), ('Second Value (Off)', 1), ('Switch Signal', 0)],
        [('Switched Value', 1)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link')],
        0),
    23: ComponentType(
        23, 'PID Controller', 'c_microprocessor_component_pid_controller',
        'control', 'mp_pid_controller',
        'A basic PID controller. The proportional, integral and derivative gains can be set in the property panel.',
        [('Setpoint', 1), ('Process Variable', 1), ('Active', 0)],
        [('Control Output', 1)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link'), ('kp', 'prop_num'), ('ki', 'prop_num'), ('kd', 'prop_num'), ('te', 'attr_float'), ('pe', 'attr_float'), ('pes', 'state')],
        0),
    24: ComponentType(
        24, 'SR Latch', 'c_microprocessor_component_sr_latch',
        'logical', 'mp_sr_latch',
        'An SR latch that can be set and reset using two on/off inputs.',
        [('Set', 0), ('Reset', 0)],
        [('Output', 0), ('NOT Output', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out'), ('out2', 'state_out'), ('p1', 'state'), ('p2', 'state')],
        0),
    25: ComponentType(
        25, 'JK Flip Flop', 'c_microprocessor_component_jk_flip_flop',
        'logical', 'mp_jk_flipflop',
        'An JK flip flop that can be set and reset using two on/off inputs.',
        [('Set', 0), ('Reset', 0)],
        [('Output', 0), ('NOT Output', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out'), ('out2', 'state_out'), ('p1', 'state'), ('p2', 'state')],
        0),
    26: ComponentType(
        26, 'Capacitor', 'c_microprocessor_component_capacitor',
        'control', 'mp_capacitor',
        'Charges up when receiving an on signal, then discharges over a period of time.',
        [('Charge', 0)],
        [('Stored Charge', 0)],
        [('in1', 'link'), ('out1', 'state_out'), ('ct', 'attr_float'), ('dt', 'attr_float'), ('c1', 'attr_int'), ('c2', 'attr_int'), ('p', 'state')],
        0),
    27: ComponentType(
        27, 'Blinker', 'c_microprocessor_component_blinker',
        'control', 'mp_blinker',
        'Outputs a value that blinks between on and off at a set rate.',
        [('Control Signal', 0)],
        [('Blinking Signal', 0)],
        [('in1', 'link'), ('out1', 'state_out'), ('on', 'attr_float'), ('off', 'attr_float'), ('c', 'attr_int')],
        0),
    28: ComponentType(
        28, 'Push To Toggle', 'c_microprocessor_component_push_to_toggle',
        'logical', 'mp_push_to_toggle',
        'An on/off switch that is toggled every time a new on signal is sent to its input.',
        [('Toggle Signal', 0)],
        [('Internal State', 0)],
        [('in1', 'link'), ('out1', 'state_out'), ('p', 'state')],
        0),
    29: ComponentType(
        29, 'Composite Read (on/off)', 'c_microprocessor_component_composite_read_bool',
        'composite', 'mp_composite_read',
        'Reads the on/off value from a selected channel of a composite input.',
        [('Composite Signal', 5), ('Start Channel', 1)],
        [('Read Value', 0)],
        [('in1', 'link'), ('out1', 'state_out'), ('i', 'attr_int'), ('in2', 'link')],
        0),
    30: ComponentType(
        30, 'Composite Write (on/off)', 'c_microprocessor_component_composite_write_bool',
        'composite', 'mp_composite_write',
        'Writes an on/off value to a selected channel of the composite input.',
        [('Composite Signal', 5), ('Set Value', 0)],
        [('Modified Composite Signal', 5)],
        [('in1', 'link'), ('in2', 'link'), ('i', 'attr_int')],
        0),
    31: ComponentType(
        31, 'Composite Read (number)', 'c_microprocessor_component_composite_read_f32',
        'composite', 'mp_composite_read',
        'Reads the number value from a selected channel of a composite input.',
        [('Composite Signal', 5), ('Start Channel', 1)],
        [('Read Value', 1)],
        [('in1', 'link'), ('i', 'attr_int'), ('in2', 'link')],
        0),
    32: ComponentType(
        32, 'Composite Write (number)', 'c_microprocessor_component_composite_write_f32',
        'composite', 'mp_composite_write',
        'Writes a number value to a selected channel of the composite input.',
        [('Composite Signal', 5), ('Set Value', 1)],
        [('Modified Composite Signal', 5)],
        [('in1', 'link'), ('in2', 'link'), ('i', 'attr_int')],
        0),
    33: ComponentType(
        33, 'Property Toggle', 'c_microprocessor_component_property_toggle',
        'property', 'mp_property_toggle',
        "Adds a custom on/off toggle that will be seen on the microcontroller's property panel when placed on a vehicle.",
        [],
        [('Toggle Value', 0)],
        [('out1', 'state_out'), ('n', 'attr_str'), ('on', 'attr_str'), ('off', 'attr_str'), ('v', 'state')],
        0),
    34: ComponentType(
        34, 'Property Number', 'c_microprocessor_component_property_number',
        'property', 'mp_property_number',
        "Adds a custom number input that will be seen on the microcontroller's property panel when placed on a vehicle.",
        [],
        [('Set Number', 1)],
        [('n', 'attr_str'), ('v', 'prop_num')],
        0),
    35: ComponentType(
        35, 'Delta', 'c_microprocessor_component_delta',
        'arithmetic', 'mp_delta',
        'Outputs the difference between the input and the input from the previous tick.',
        [('Input Value', 1)],
        [('Delta Of Input Value', 1)],
        [('in1', 'link'), ('vp', 'attr_float'), ('ip', 'state')],
        0),
    36: ComponentType(
        36, 'f(x, y, z, w, a, b, c, d)', 'c_microprocessor_component_function_8_inputs',
        'arithmetic', 'mp_function',
        'Evaluates a mathematical expression with up to 8 input variables and outputs the result.',
        [('x', 1), ('y', 1), ('z', 1), ('w', 1), ('a', 1), ('b', 1), ('c', 1), ('d', 1)],
        [('f(x, y, z, w, a, b, c, d)', 1)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link'), ('in4', 'link'), ('in5', 'link'), ('in6', 'link'), ('in7', 'link'), ('in8', 'link'), ('e', 'attr_str')],
        0),
    37: ComponentType(
        37, 'Up/Down Counter', 'c_microprocessor_component_up_down',
        'control', 'mp_up_down',
        'Has an internal value that will increase and decrease when receiving different signals.',
        [('Up', 0), ('Down', 0), ('Reset', 0)],
        [('Value', 1)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link'), ('r', 'prop_num'), ('i', 'prop_num'), ('m', 'attr_int'), ('min', 'prop_num'), ('max', 'prop_num'), ('is', 'state')],
        0),
    38: ComponentType(
        38, 'Modulo (fmod)', 'c_microprocessor_component_modulo',
        'arithmetic', 'mp_modulo',
        'Outputs the modulo of input A by input B.',
        [('A', 1), ('B', 1)],
        [('A % B', 1)],
        [('in1', 'link'), ('in2', 'link')],
        0),
    39: ComponentType(
        39, 'PID Controller (Advanced)', 'c_microprocessor_component_advanced_pid',
        'control', 'mp_pid_controller',
        'A PID controller with variable proportional, integral and derivative gains.',
        [('Setpoint', 1), ('Process Variable', 1), ('Proportional Gain', 1), ('Integral Gain', 1), ('Derivative Gain', 1), ('Active', 0)],
        [('Control Output', 1)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link'), ('in4', 'link'), ('in5', 'link'), ('in6', 'link'), ('te', 'attr_float'), ('pe', 'attr_float'), ('pes', 'state')],
        0),
    40: ComponentType(
        40, 'Composite Write (number)', 'c_microprocessor_component_composite_write_f32_large',
        'composite', 'mp_composite_write',
        'Writes up to 32 numbers to a composite link in a single logic tick. Only connected channels will be modified. The ',
        [('Composite Signal', 5), ('Input 1', 1), ('Input 2', 1), ('Input 3', 1), ('Input 4', 1), ('Input 5', 1), ('Input 6', 1), ('Input 7', 1), ('Input 8', 1), ('Input 9', 1), ('Input 10', 1), ('Input 11', 1), ('Input 12', 1), ('Input 13', 1), ('Input 14', 1), ('Input 15', 1), ('Input 16', 1), ('Input 17', 1), ('Input 18', 1), ('Input 19', 1), ('Input 20', 1), ('Input 21', 1), ('Input 22', 1), ('Input 23', 1), ('Input 24', 1), ('Input 25', 1), ('Input 26', 1), ('Input 27', 1), ('Input 28', 1), ('Input 29', 1), ('Input 30', 1), ('Input 31', 1), ('Input 32', 1), ('Start Channel', 1)],
        [('Modified Composite Signal', 5)],
        [('inc', 'link'), ('count', 'attr_int'), ('offset', 'attr_int'), ('in%u', 'link'), ('inoff', 'link')],
        32),
    41: ComponentType(
        41, 'Composite Write (on/off)', 'c_microprocessor_component_composite_write_bool_large',
        'composite', 'mp_composite_write',
        'Writes up to 32 on/off signals to a composite link in a single logic tick. Only connected channels will be modifie',
        [('Composite Signal', 5), ('Input 1', 0), ('Input 2', 0), ('Input 3', 0), ('Input 4', 0), ('Input 5', 0), ('Input 6', 0), ('Input 7', 0), ('Input 8', 0), ('Input 9', 0), ('Input 10', 0), ('Input 11', 0), ('Input 12', 0), ('Input 13', 0), ('Input 14', 0), ('Input 15', 0), ('Input 16', 0), ('Input 17', 0), ('Input 18', 0), ('Input 19', 0), ('Input 20', 0), ('Input 21', 0), ('Input 22', 0), ('Input 23', 0), ('Input 24', 0), ('Input 25', 0), ('Input 26', 0), ('Input 27', 0), ('Input 28', 0), ('Input 29', 0), ('Input 30', 0), ('Input 31', 0), ('Input 32', 0), ('Start Channel', 1)],
        [('Modified Composite Signal', 5)],
        [('inc', 'link'), ('count', 'attr_int'), ('offset', 'attr_int'), ('in%u', 'link'), ('inoff', 'link')],
        32),
    42: ComponentType(
        42, 'Equal', 'c_microprocessor_component_equal',
        'arithmetic', 'mp_equal',
        'Compares whether or not two numbers are equal within a set accuracy.',
        [('A', 1), ('B', 1)],
        [('A = B', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out'), ('e', 'prop_num')],
        0),
    43: ComponentType(
        43, 'Tooltip Number', 'c_microprocessor_component_property_output_number',
        'property', 'mp_tooltip_number',
        "Displays a number on this microcontroller's tooltip when it is looked at by the player on a spawned vehicle.",
        [('Display Number', 1), ('Is Error', 0)],
        [],
        [('in1', 'link'), ('in2', 'link'), ('l', 'attr_str'), ('m', 'attr_int')],
        0),
    44: ComponentType(
        44, 'Tooltip On/Off', 'c_microprocessor_component_property_output_bool',
        'property', 'mp_tooltip_bool',
        "Displays an on/off signal on this microcontroller's tooltip when it is looked at by the player on a spawned vehicle.",
        [('Display Signal', 0)],
        [],
        [('in1', 'link'), ('l', 'attr_str'), ('on', 'attr_str'), ('off', 'attr_str'), ('m', 'attr_int')],
        0),
    45: ComponentType(
        45, 'f(x)', 'c_microprocessor_component_function_1_input',
        'arithmetic', 'mp_function',
        'Evaluates a mathematical expression with 1 input variable and outputs the result.',
        [('x', 1)],
        [('f(x)', 1)],
        [('in1', 'link'), ('e', 'attr_str')],
        0),
    46: ComponentType(
        46, 'Boolean f(x,y,z,w)', 'c_microprocessor_component_function_bool_4_inputs',
        'logical', 'mp_function',
        'Evaluates a logical expression with up to 4 input variables and outputs the result.',
        [('x', 0), ('y', 0), ('z', 0), ('w', 0)],
        [('f(x,y,z,w)', 0)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link'), ('in4', 'link'), ('out1', 'state_out'), ('e', 'attr_str')],
        0),
    47: ComponentType(
        47, 'Boolean f(x,y,z,w,a,b,c,d)', 'c_microprocessor_component_function_bool_8_inputs',
        'logical', 'mp_function',
        'Evaluates a logical expression with up to 8 input variables and outputs the result.',
        [('x', 0), ('y', 0), ('z', 0), ('w', 0), ('a', 0), ('b', 0), ('c', 0), ('d', 0)],
        [('f(x,y,z,w,a,b,c,d)', 0)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link'), ('in4', 'link'), ('in5', 'link'), ('in6', 'link'), ('in7', 'link'), ('in8', 'link'), ('out1', 'state_out'), ('e', 'attr_str')],
        0),
    48: ComponentType(
        48, 'Pulse (Toggle to Push)', 'c_microprocessor_component_pulse',
        'logical', 'mp_pulse',
        'A switch that outputs a single tick pulse. It can be configured to pulse when being switched from off to on (defau',
        [('Toggle Signal', 0)],
        [('Pulse', 0)],
        [('in1', 'link'), ('out1', 'state_out'), ('m', 'attr_int'), ('p', 'state')],
        0),
    49: ComponentType(
        49, 'Timer (TON)', 'c_microprocessor_component_ton',
        'control', 'mp_timer_on',
        'Variable input timer. Outputs an on signal when the timer reaches its duration. The timer will reset when off.',
        [('Timer Enable', 0), ('Duration', 1)],
        [('Timing Complete', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out'), ('u', 'attr_int'), ('t', 'attr_float')],
        0),
    50: ComponentType(
        50, 'Timer (TOF)', 'c_microprocessor_component_tof',
        'control', 'mp_timer_off',
        'Variable input timer. Outputs an on signal when the timer is less than its duration. The timer will reset when off.',
        [('Timer Enable', 0), ('Duration', 1)],
        [('Timing', 0)],
        [('in1', 'link'), ('in2', 'link'), ('out1', 'state_out'), ('u', 'attr_int'), ('t', 'attr_float')],
        0),
    51: ComponentType(
        51, 'Timer (RTO)', 'c_microprocessor_component_rto',
        'control', 'mp_timer_on',
        'Variable input timer. Outputs an on signal when the timer reaches its duration. The timer will not reset until it is signalled.',
        [('Timer Enable', 0), ('Duration', 1), ('Reset', 0)],
        [('Timing Complete', 0)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link'), ('out1', 'state_out'), ('u', 'attr_int'), ('t', 'attr_float')],
        0),
    52: ComponentType(
        52, 'Timer (RTF)', 'c_microprocessor_component_rtf',
        'control', 'mp_timer_off',
        'Variable input timer. Outputs an on signal when the timer is less than its duration. The timer will not reset unti',
        [('Timer Enable', 0), ('Duration', 1), ('Reset', 0)],
        [('Timing', 0)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link'), ('out1', 'state_out'), ('u', 'attr_int'), ('t', 'attr_float')],
        0),
    53: ComponentType(
        53, 'Composite Switchbox', 'c_microprocessor_component_composite_switchbox',
        'composite', 'mp_numerical_switchbox',
        'Outputs the first input composite when receiving an on signal, and the second when receiving an off signal.',
        [('First Signal (On)', 5), ('Second Signal (Off)', 5), ('Switch Signal', 0)],
        [('Switched Signal', 5)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link')],
        0),
    54: ComponentType(
        54, 'Number To Composite Binary', 'c_microprocessor_component_number_to_composite_binary',
        'composite', 'mp_binary',
        'Converts a number (rounded) to binary and outputs the bits as composite on/off signals.',
        [('Number To Convert', 1)],
        [('Binary Signal', 5)],
        [('in1', 'link')],
        0),
    55: ComponentType(
        55, 'Composite Binary To Number', 'c_microprocessor_component_composite_binary_to_number',
        'composite', 'mp_binary',
        'Reads the on/off signals of a composite link and encodes them in the bits of an output number.',
        [('Signal To Convert', 5)],
        [('Encoded Number', 1)],
        [('in1', 'link')],
        0),
    56: ComponentType(
        56, 'Lua Script', 'c_microprocessor_component_lua_script',
        'composite', 'mp_lua_script',
        'Runs a custom lua script for advanced logic and drawing to monitors.',
        [('Data Input', 5), ('Video Input', 6)],
        [('Data Output', 5), ('Video Output', 6)],
        [('in1', 'link'), ('in2', 'link'), ('out2', 'state_out'), ('script', 'attr_str')],
        0),
    57: ComponentType(
        57, 'Video Switchbox', 'c_microprocessor_component_video_switchbox',
        'composite', 'mp_video_switchbox',
        'Outputs the first input video when receiving an on signal, and the second when receiving an off signal.',
        [('Video 1 (On)', 6), ('Video 2 (Off)', 6), ('Switch Signal', 0)],
        [('Video Output', 6)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link'), ('out1', 'state_out')],
        0),
    58: ComponentType(
        58, 'Property Text', 'c_microprocessor_component_property_text',
        'property', 'mp_property_number',
        "Adds a custom text input that will be seen on the microcontroller's property panel when placed on a vehicle, for s",
        [],
        [],
        [('n', 'attr_str'), ('v', 'attr_str')],
        0),
    59: ComponentType(
        59, 'Audio Switchbox', 'c_microprocessor_component_audio_switchbox',
        'composite', 'mp_audio_switchbox',
        'Outputs the first input audio when receiving an on signal, and the second when receiving an off signal.',
        [('Audio 1 (On)', 7), ('Audio 2 (Off)', 7), ('Switch Signal', 0)],
        [('Audio Output', 7)],
        [('in1', 'link'), ('in2', 'link'), ('in3', 'link')],
        0),
}

BRIDGE_TYPES = {
    0: ComponentType(
        0, 'Bool input', 'c_microprocessor_component_bridge_bool_input',
        'bridge', None,
        'Microprocessor input pin carrying a bool signal.',
        [],
        [],
        [('in1', 'link'), ('out1', 'state_out')],
        0),
    1: ComponentType(
        1, 'Bool output', 'c_microprocessor_component_bridge_bool_output',
        'bridge', None,
        'Microprocessor output pin carrying a bool signal.',
        [],
        [],
        [('in1', 'link'), ('out1', 'state_out')],
        0),
    2: ComponentType(
        2, 'Number input', 'c_microprocessor_component_bridge_f32_input',
        'bridge', None,
        'Microprocessor input pin carrying a number signal.',
        [],
        [],
        [('in1', 'link')],
        0),
    3: ComponentType(
        3, 'Number output', 'c_microprocessor_component_bridge_f32_output',
        'bridge', None,
        'Microprocessor output pin carrying a number signal.',
        [],
        [],
        [('in1', 'link')],
        0),
    4: ComponentType(
        4, 'Composite input', 'c_microprocessor_component_bridge_composite_input',
        'bridge', None,
        'Microprocessor input pin carrying a composite signal.',
        [],
        [],
        [('in1', 'link')],
        0),
    5: ComponentType(
        5, 'Composite output', 'c_microprocessor_component_bridge_composite_output',
        'bridge', None,
        'Microprocessor output pin carrying a composite signal.',
        [],
        [],
        [('in1', 'link')],
        0),
    6: ComponentType(
        6, 'Video input', 'c_microprocessor_component_bridge_video_input',
        'bridge', None,
        'Microprocessor input pin carrying a video signal.',
        [],
        [],
        [('in1', 'link'), ('out1', 'state_out')],
        0),
    7: ComponentType(
        7, 'Video output', 'c_microprocessor_component_bridge_video_output',
        'bridge', None,
        'Microprocessor output pin carrying a video signal.',
        [],
        [],
        [('in1', 'link'), ('out1', 'state_out')],
        0),
    8: ComponentType(
        8, 'Audio input', 'c_microprocessor_component_bridge_audio_input',
        'bridge', None,
        'Microprocessor input pin carrying a audio signal.',
        [],
        [],
        [('in1', 'link')],
        0),
    9: ComponentType(
        9, 'Audio output', 'c_microprocessor_component_bridge_audio_output',
        'bridge', None,
        'Microprocessor output pin carrying a audio signal.',
        [],
        [],
        [('in1', 'link')],
        0),
}

#: name -> type id, for every component type (case-insensitive lookups go via
#: :func:`find_type`).
COMPONENT_TYPES_BY_NAME = {t.name.lower(): t for t in COMPONENT_TYPES.values()}

#: Short aliases so callers can say "add" or "func8" instead of the display name.
ALIASES = {
    'not': 0,
    'and': 1,
    'or': 2,
    'xor': 3,
    'nand': 4,
    'nor': 5,
    'add': 6,
    'sub': 7,
    'subtract': 7,
    'mul': 8,
    'multiply': 8,
    'div': 9,
    'divide': 9,
    'func3': 10,
    'function': 10,
    'clamp': 11,
    'threshold': 12,
    'memory': 13,
    'abs': 14,
    'const': 15,
    'constnum': 15,
    'constbool': 16,
    'const_on': 16,
    'gt': 17,
    'greater': 17,
    'lt': 18,
    'less': 18,
    'slider': 19,
    'dropdown': 20,
    'junction': 21,
    'switchbox': 22,
    'pid': 23,
    'srlatch': 24,
    'jk': 25,
    'capacitor': 26,
    'blinker': 27,
    'toggle': 28,
    'cread_bool': 29,
    'cwrite_bool': 30,
    'cread_num': 31,
    'cwrite_num': 32,
    'prop_toggle': 33,
    'prop_number': 34,
    'delta': 35,
    'func8': 36,
    'updown': 37,
    'mod': 38,
    'modulo': 38,
    'pid_adv': 39,
    'cwrite_num32': 40,
    'cwrite_bool32': 41,
    'equal': 42,
    'tooltip_num': 43,
    'tooltip_bool': 44,
    'func1': 45,
    'bfunc4': 46,
    'bfunc8': 47,
    'pulse': 48,
    'ton': 49,
    'tof': 50,
    'rto': 51,
    'rtf': 52,
    'cswitchbox': 53,
    'num2bin': 54,
    'bin2num': 55,
    'lua': 56,
    'vswitchbox': 57,
    'prop_text': 58,
    'aswitchbox': 59,
}


def find_type(key: "Union[int, str, ComponentType]") -> ComponentType:
    """Resolve a component type from an id, an alias, or a display name."""
    if isinstance(key, ComponentType):
        return key
    if isinstance(key, int):
        return COMPONENT_TYPES[key]
    s = str(key).strip()
    if s.isdigit():
        return COMPONENT_TYPES[int(s)]
    low = s.lower()
    if low in ALIASES:
        return COMPONENT_TYPES[ALIASES[low]]
    if low in COMPONENT_TYPES_BY_NAME:
        return COMPONENT_TYPES_BY_NAME[low]
    hits = [t for t in COMPONENT_TYPES.values() if low in t.name.lower()]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise UnknownTypeError("ambiguous component type %r: %s"
                               % (key, ", ".join("%d=%s" % (t.type_id, t.name)
                                                 for t in hits)))
    raise UnknownTypeError("unknown component type %r" % (key,))
