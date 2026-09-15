# Stormworks microprocessor component types

`<c type="N">` inside `<group><components>`. Extracted from `stormworks64.exe`: the 60-entry table at `qword_140D1B088` built by `sub_140367330`, and the factory `sub_14038BD80`.

Data types: `b` on/off, `n` number, `c` composite, `v` video, `a` audio.

| type | name | aliases | cat | inputs | outputs | properties |
|---:|---|---|---|---|---|---|
| 0 | NOT | `not` | logical | in1:b | #0:b | — |
| 1 | AND | `and` | logical | in1:b in2:b | #0:b | — |
| 2 | OR | `or` | logical | in1:b in2:b | #0:b | — |
| 3 | XOR | `xor` | logical | in1:b in2:b | #0:b | — |
| 4 | NAND | `nand` | logical | in1:b in2:b | #0:b | — |
| 5 | NOR | `nor` | logical | in1:b in2:b | #0:b | — |
| 6 | Add | `add` | arithmetic | in1:n in2:n | #0:n | — |
| 7 | Subtract | `sub` `subtract` | arithmetic | in1:n in2:n | #0:n | — |
| 8 | Multiply | `mul` `multiply` | arithmetic | in1:n in2:n | #0:n | — |
| 9 | Divide | `div` `divide` | arithmetic | in1:n in2:n | #0:n #1:b | — |
| 10 | f(x, y, z) | `func3` `function` | arithmetic | in1:n in2:n in3:n | #0:n | `e` `p1` `p2` `p3` |
| 11 | Clamp | `clamp` | arithmetic | in1:n | #0:n | `min` `max` |
| 12 | Threshold | `threshold` | control | in1:n | #0:b | `min` `max` |
| 13 | Memory Register | `memory` | control | in1:b in2:b in3:n | #0:n | `memory` `r` |
| 14 | Abs | `abs` | arithmetic | in1:n | #0:n | — |
| 15 | Constant Number | `const` `constnum` | arithmetic | — | #0:n | `n` |
| 16 | Constant On Signal | `const_on` `constbool` | logical | — | #0:b | — |
| 17 | Greater Than | `greater` `gt` | control | in1:n in2:n | #0:b | — |
| 18 | Less Than | `less` `lt` | control | in1:n in2:n | #0:b | — |
| 19 | Property Slider | `slider` | property | — | #0:n | `name` `min` `max` `int` `v` |
| 20 | Property Dropdown | `dropdown` | property | — | #0:n | `name` `v` `i` |
| 21 | Numerical Junction | `junction` | control | in1:n in2:b | #0:n #1:n | — |
| 22 | Numerical Switchbox | `switchbox` | control | in1:n in2:n in3:b | #0:n | — |
| 23 | PID Controller | `pid` | control | in1:n in2:n in3:b | #0:n | `kp` `ki` `kd` `te` `pe` |
| 24 | SR Latch | `srlatch` | logical | in1:b in2:b | #0:b #1:b | — |
| 25 | JK Flip Flop | `jk` | logical | in1:b in2:b | #0:b #1:b | — |
| 26 | Capacitor | `capacitor` | control | in1:b | #0:b | `ct` `dt` `c1` `c2` |
| 27 | Blinker | `blinker` | control | in1:b | #0:b | `on` `off` `c` |
| 28 | Push To Toggle | `toggle` | logical | in1:b | #0:b | — |
| 29 | Composite Read (on/off) | `cread_bool` | composite | in1:c in2:n | #0:b | `i` |
| 30 | Composite Write (on/off) | `cwrite_bool` | composite | in1:c in2:b | #0:c | `i` |
| 31 | Composite Read (number) | `cread_num` | composite | in1:c in2:n | #0:n | `i` |
| 32 | Composite Write (number) | `cwrite_num` | composite | in1:c in2:n | #0:c | `i` |
| 33 | Property Toggle | `prop_toggle` | property | — | #0:b | `n` `on` `off` |
| 34 | Property Number | `prop_number` | property | — | #0:n | `n` `v` |
| 35 | Delta | `delta` | arithmetic | in1:n | #0:n | `vp` |
| 36 | f(x, y, z, w, a, b, c, d) | `func8` | arithmetic | in1:n in2:n in3:n in4:n in5:n in6:n in7:n in8:n | #0:n | `e` |
| 37 | Up/Down Counter | `updown` | control | in1:b in2:b in3:b | #0:n | `r` `i` `m` `min` `max` |
| 38 | Modulo (fmod) | `mod` `modulo` | arithmetic | in1:n in2:n | #0:n | — |
| 39 | PID Controller (Advanced) | `pid_adv` | control | in1:n in2:n in3:n in4:n in5:n in6:b | #0:n | `te` `pe` |
| 40 | Composite Write (number) | `cwrite_num32` | composite | inc:c in1..in32:n inoff:n | #0:c | `count` `offset` |
| 41 | Composite Write (on/off) | `cwrite_bool32` | composite | inc:c in1..in32:b inoff:n | #0:c | `count` `offset` |
| 42 | Equal | `equal` | arithmetic | in1:n in2:n | #0:b | `e` |
| 43 | Tooltip Number | `tooltip_num` | property | in1:n in2:b | — | `l` `m` |
| 44 | Tooltip On/Off | `tooltip_bool` | property | in1:b | — | `l` `on` `off` `m` |
| 45 | f(x) | `func1` | arithmetic | in1:n | #0:n | `e` |
| 46 | Boolean f(x,y,z,w) | `bfunc4` | logical | in1:b in2:b in3:b in4:b | #0:b | `e` |
| 47 | Boolean f(x,y,z,w,a,b,c,d) | `bfunc8` | logical | in1:b in2:b in3:b in4:b in5:b in6:b in7:b in8:b | #0:b | `e` |
| 48 | Pulse (Toggle to Push) | `pulse` | logical | in1:b | #0:b | `m` |
| 49 | Timer (TON) | `ton` | control | in1:b in2:n | #0:b | `u` `t` |
| 50 | Timer (TOF) | `tof` | control | in1:b in2:n | #0:b | `u` `t` |
| 51 | Timer (RTO) | `rto` | control | in1:b in2:n in3:b | #0:b | `u` `t` |
| 52 | Timer (RTF) | `rtf` | control | in1:b in2:n in3:b | #0:b | `u` `t` |
| 53 | Composite Switchbox | `cswitchbox` | composite | in1:c in2:c in3:b | #0:c | — |
| 54 | Number To Composite Binary | `num2bin` | composite | in1:n | #0:c | — |
| 55 | Composite Binary To Number | `bin2num` | composite | in1:c | #0:n | — |
| 56 | Lua Script | `lua` | composite | in1:c in2:v | #0:c #1:v | `script` |
| 57 | Video Switchbox | `vswitchbox` | composite | in1:v in2:v in3:b | #0:v | — |
| 58 | Property Text | `prop_text` | property | — | — | `n` `v` |
| 59 | Audio Switchbox | `aswitchbox` | composite | in1:a in2:a in3:b | #0:a | — |

## Input labels

`connect` accepts these labels as well as `in1`/index form.

- **0 NOT** — `in1` = A
- **1 AND** — `in1` = A, `in2` = B
- **2 OR** — `in1` = A, `in2` = B
- **3 XOR** — `in1` = A, `in2` = B
- **4 NAND** — `in1` = A, `in2` = B
- **5 NOR** — `in1` = A, `in2` = B
- **6 Add** — `in1` = A, `in2` = B
- **7 Subtract** — `in1` = A, `in2` = B
- **8 Multiply** — `in1` = A, `in2` = B
- **9 Divide** — `in1` = A, `in2` = B
- **10 f(x, y, z)** — `in1` = x, `in2` = y, `in3` = z
- **11 Clamp** — `in1` = Input Number
- **12 Threshold** — `in1` = Input Number
- **13 Memory Register** — `in1` = Set, `in2` = Reset, `in3` = Number to store
- **14 Abs** — `in1` = Input Number
- **17 Greater Than** — `in1` = A, `in2` = B
- **18 Less Than** — `in1` = A, `in2` = B
- **21 Numerical Junction** — `in1` = Value To Pass Through, `in2` = Switch Signal
- **22 Numerical Switchbox** — `in1` = First Value (On), `in2` = Second Value (Off), `in3` = Switch Signal
- **23 PID Controller** — `in1` = Setpoint, `in2` = Process Variable, `in3` = Active
- **24 SR Latch** — `in1` = Set, `in2` = Reset
- **25 JK Flip Flop** — `in1` = Set, `in2` = Reset
- **26 Capacitor** — `in1` = Charge
- **27 Blinker** — `in1` = Control Signal
- **28 Push To Toggle** — `in1` = Toggle Signal
- **29 Composite Read (on/off)** — `in1` = Composite Signal, `in2` = Start Channel
- **30 Composite Write (on/off)** — `in1` = Composite Signal, `in2` = Set Value
- **31 Composite Read (number)** — `in1` = Composite Signal, `in2` = Start Channel
- **32 Composite Write (number)** — `in1` = Composite Signal, `in2` = Set Value
- **35 Delta** — `in1` = Input Value
- **36 f(x, y, z, w, a, b, c, d)** — `in1` = x, `in2` = y, `in3` = z, `in4` = w, `in5` = a, `in6` = b, `in7` = c, `in8` = d
- **37 Up/Down Counter** — `in1` = Up, `in2` = Down, `in3` = Reset
- **38 Modulo (fmod)** — `in1` = A, `in2` = B
- **39 PID Controller (Advanced)** — `in1` = Setpoint, `in2` = Process Variable, `in3` = Proportional Gain, `in4` = Integral Gain, `in5` = Derivative Gain, `in6` = Active
- **40 Composite Write (number)** — `inc` = Composite Signal, `in1` = Input 1, `in2` = Input 2, `in3` = Input 3, `in4` = Input 4, `in5` = Input 5, `in6` = Input 6, `in7` = Input 7, `in8` = Input 8, `in9` = Input 9, `in10` = Input 10, `in11` = Input 11, `in12` = Input 12, `in13` = Input 13, `in14` = Input 14, `in15` = Input 15, `in16` = Input 16, `in17` = Input 17, `in18` = Input 18, `in19` = Input 19, `in20` = Input 20, `in21` = Input 21, `in22` = Input 22, `in23` = Input 23, `in24` = Input 24, `in25` = Input 25, `in26` = Input 26, `in27` = Input 27, `in28` = Input 28, `in29` = Input 29, `in30` = Input 30, `in31` = Input 31, `in32` = Input 32, `inoff` = Start Channel
- **41 Composite Write (on/off)** — `inc` = Composite Signal, `in1` = Input 1, `in2` = Input 2, `in3` = Input 3, `in4` = Input 4, `in5` = Input 5, `in6` = Input 6, `in7` = Input 7, `in8` = Input 8, `in9` = Input 9, `in10` = Input 10, `in11` = Input 11, `in12` = Input 12, `in13` = Input 13, `in14` = Input 14, `in15` = Input 15, `in16` = Input 16, `in17` = Input 17, `in18` = Input 18, `in19` = Input 19, `in20` = Input 20, `in21` = Input 21, `in22` = Input 22, `in23` = Input 23, `in24` = Input 24, `in25` = Input 25, `in26` = Input 26, `in27` = Input 27, `in28` = Input 28, `in29` = Input 29, `in30` = Input 30, `in31` = Input 31, `in32` = Input 32, `inoff` = Start Channel
- **42 Equal** — `in1` = A, `in2` = B
- **43 Tooltip Number** — `in1` = Display Number, `in2` = Is Error
- **44 Tooltip On/Off** — `in1` = Display Signal
- **45 f(x)** — `in1` = x
- **46 Boolean f(x,y,z,w)** — `in1` = x, `in2` = y, `in3` = z, `in4` = w
- **47 Boolean f(x,y,z,w,a,b,c,d)** — `in1` = x, `in2` = y, `in3` = z, `in4` = w, `in5` = a, `in6` = b, `in7` = c, `in8` = d
- **48 Pulse (Toggle to Push)** — `in1` = Toggle Signal
- **49 Timer (TON)** — `in1` = Timer Enable, `in2` = Duration
- **50 Timer (TOF)** — `in1` = Timer Enable, `in2` = Duration
- **51 Timer (RTO)** — `in1` = Timer Enable, `in2` = Duration, `in3` = Reset
- **52 Timer (RTF)** — `in1` = Timer Enable, `in2` = Duration, `in3` = Reset
- **53 Composite Switchbox** — `in1` = First Signal (On), `in2` = Second Signal (Off), `in3` = Switch Signal
- **54 Number To Composite Binary** — `in1` = Number To Convert
- **55 Composite Binary To Number** — `in1` = Signal To Convert
- **56 Lua Script** — `in1` = Data Input, `in2` = Video Input
- **57 Video Switchbox** — `in1` = Video 1 (On), `in2` = Video 2 (Off), `in3` = Switch Signal
- **59 Audio Switchbox** — `in1` = Audio 1 (On), `in2` = Audio 2 (Off), `in3` = Switch Signal

## Bridge (external pin) types

`<c type="N">` inside `<components_bridge>` — a separate enum from the table above. Factory `sub_14038CA00`.

| type | meaning | class |
|---:|---|---|
| 0 | Bool input | `c_microprocessor_component_bridge_bool_input` |
| 1 | Bool output | `c_microprocessor_component_bridge_bool_output` |
| 2 | Number input | `c_microprocessor_component_bridge_f32_input` |
| 3 | Number output | `c_microprocessor_component_bridge_f32_output` |
| 4 | Composite input | `c_microprocessor_component_bridge_composite_input` |
| 5 | Composite output | `c_microprocessor_component_bridge_composite_output` |
| 6 | Video input | `c_microprocessor_component_bridge_video_input` |
| 7 | Video output | `c_microprocessor_component_bridge_video_output` |
| 8 | Audio input | `c_microprocessor_component_bridge_audio_input` |
| 9 | Audio output | `c_microprocessor_component_bridge_audio_output` |

## Property field kinds

| kind | XML |
|---|---|
| `attr_str` | attribute on `<object>`, e.g. `e="x+y"` |
| `attr_int` | attribute, integer, e.g. `i="10"` |
| `attr_float` | attribute, float, e.g. `t="0.5"` |
| `prop_num` | child element `<min text="-0.1" value="-0.1"/>` |

`prop_num` keeps `text` (what the player typed, which may be an expression) apart from `value` (the evaluated number).
