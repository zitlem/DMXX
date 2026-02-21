"""Help/documentation API endpoints."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/help")
async def get_help():
    """Return comprehensive documentation about the I/O system."""
    return {
        "title": "DMXX Input/Output System Documentation",
        "sections": {
            "io_flow": {
                "title": "I/O Signal Flow",
                "description": "How DMX signals flow through the system in different modes",
                "flows": [
                    {
                        "mode": "Input Off (Passthrough: Off)",
                        "diagram": """+---------------+     +-------------+     +------------+
| Local         | --> | Universe GM | --> | Global GM  | --> OUTPUT
| Faders        |     | (per univ)  |     | (all univ) |
+---------------+     +-------------+     +------------+""",
                        "description": "No external input. Output comes only from your local fader values, scaled by grandmasters."
                    },
                    {
                        "mode": "Groups with Local Control (No Input)",
                        "diagram": """+---------------+     +----------+     +-------------+     +------------+
| Local Group   | --> | Group    | --> | Universe GM | --> | Global GM  | --> OUTPUT
| Master Fader  |     | Members  |     | (per univ)  |     | (all univ) |
+---------------+     +----------+     +-------------+     +------------+
        |
        v
+---------------+
| Mode:         |
| Proportional: member = base × (master / 255)
| Follow: member = master
+---------------+""",
                        "description": "Groups controlled by local master faders. Moving a group fader calculates member channel values based on the group mode (Proportional or Follow)."
                    },
                    {
                        "mode": "View Only (Passthrough: View Only)",
                        "diagram": """+---------------+     +---------------+
| External      | --> | UI Display    |  (view only, no output)
| Input         |     | on Faders     |
+---------------+     +---------------+

+---------------+     +-------------+     +------------+
| Local         | --> | Universe GM | --> | Global GM  | --> OUTPUT
| Faders        |     +-------------+     +------------+
+---------------+""",
                        "description": "Input displayed on faders for monitoring. Your local fader values (set by dragging) go to output, scaled by grandmasters."
                    },
                    {
                        "mode": "Groups with View Only",
                        "diagram": """+---------------+     +---------------+
| External      | --> | UI Display    |  (view only, no output)
| Input         |     | on Faders     |
+---------------+     +---------------+

+---------------+     +----------+     +-------------+     +------------+
| Local Group   | --> | Group    | --> | Universe GM | --> | Global GM  | --> OUTPUT
| Master Fader  |     | Members  |     +-------------+     +------------+
+---------------+     +----------+""",
                        "description": "Input displayed for monitoring while groups are controlled locally via their master faders."
                    },
                    {
                        "mode": "Faders + Output (Passthrough: Faders + Output)",
                        "diagram": """+----------+     +---------+     +---------+     +-----------+     +----------+
| External | --> | Channel | --> |  MERGE  | --> | Universe  | --> | Global   | --> OUTPUT
| Input    |     | Mapping |     | (HTP/   |     | GM        |     | GM       |
+----------+     +---------+     |  LTP)   |     +-----------+     +----------+
                                 |         |
+----------+                     |         |
| Local    | ------------------> |         |
| Faders   |                     +---------+
+----------+""",
                        "description": "Input merged with local faders, then scaled by universe and global grandmasters."
                    },
                    {
                        "mode": "Bypass Active (any mode)",
                        "diagram": """+---------------+     +---------------+
| External      | --> | UI Display    |  X BLOCKED
| Input         |     | (optional)    | ---X----------> (no output)
+---------------+     +---------------+

+---------------+     +-------------+     +------------+
| Local         | --> | Universe GM | --> | Global GM  | --> OUTPUT
| Faders        |     +-------------+     +------------+
+---------------+           (full control)""",
                        "description": "Bypass blocks input from output. Local faders have full control, scaled by grandmasters."
                    },
                    {
                        "mode": "Groups with DMX Input Link (Faders + Output)",
                        "diagram": """+----------+     +---------+     +--------+     +---------+     +-----------+     +----------+
| External | --> | Channel | --> | Groups | --> |  MERGE  | --> | Universe  | --> | Global   | --> OUTPUT
| Input    |     | Mapping |     | (link) |     | (HTP/   |     | GM        |     | GM       |
+----------+     +---------+     +--------+     |  LTP)   |     +-----------+     +----------+
                      |                         |         |
                      +-----------------------> |         |
                      (unmapped)                |         |
                                                |         |
+----------+                                    |         |
| Local    | ---------------------------------> |         |
| Faders   |                                    +---------+
+----------+""",
                        "description": "Groups expand to member channels, merge with local faders, then scaled by grandmasters."
                    }
                ],
                "note": "Signal flow: Input → Mapping → Groups → Merge → Universe GM → Global GM → Output"
            },
            "passthrough_modes": {
                "title": "Passthrough Modes",
                "description": "Control how external DMX input is handled",
                "modes": [
                    {
                        "mode": "Off",
                        "description": "Input is disabled - no external DMX is received or displayed"
                    },
                    {
                        "mode": "View Only (faders only)",
                        "description": "Input is displayed on the faders UI for monitoring, but NOT sent to output. Important: Each fader has TWO values - the DISPLAYED value (from input) and your LOCAL value (what you control). When you drag a fader, you're setting your local value which goes to output. The display may show input, but your local value is independent."
                    },
                    {
                        "mode": "Faders + Output",
                        "description": "Input is shown on the faders UI AND merged with output. External DMX values are combined with your local fader values using the selected merge mode (HTP or LTP). Faders for input-controlled channels will snap back to their input values when moved. Configure the Input Channel Range to allow free fader control on channels outside the range."
                    }
                ],
                "example": {
                    "scenario": "External input sends 255 to channel 1 in View Only mode",
                    "result": "Fader UI shows 255, but actual output remains at your local value (e.g., 0). The input is displayed but doesn't control the lights."
                }
            },
            "input_channel_range": {
                "title": "Input Channel Range",
                "description": "Limit which channels are controlled by external input",
                "how_it_works": "By default, input controls all 512 channels. You can restrict input to a specific range (e.g., channels 1-12). Channels outside this range can be freely controlled by faders and scenes even while input is active.",
                "example": {
                    "setup": "Input Channel Range: 1-12",
                    "behavior": [
                        "Channels 1-12: Controlled by external input, faders snap back to input values",
                        "Channels 13-512: Free for manual fader control and scene recall"
                    ]
                },
                "use_case": "Perfect for a 12-channel mixing console: The console controls channels 1-12, while you use DMXX scenes and faders for channels 13-512."
            },
            "merge_modes": {
                "title": "Merge Modes",
                "description": "When passthrough is 'Faders + Output', determines how input and local values combine",
                "modes": [
                    {
                        "mode": "HTP (Highest Takes Precedence)",
                        "description": "The higher value wins. If input is 200 and local fader is 100, output is 200. If input is 50 and local is 100, output is 100."
                    },
                    {
                        "mode": "LTP (Latest Takes Precedence)",
                        "description": "The most recent change wins. If input changes to 200, output is 200. If you then move local fader to 100, output becomes 100."
                    }
                ]
            },
            "channel_mapping": {
                "title": "Channel Mapping",
                "description": "Route input channels to different output channels",
                "how_it_works": "Create mappings to redirect incoming DMX channels. For example, map Input Channel 1 to Output Channel 100. The input value arrives on channel 1 but is applied to channel 100.",
                "unmapped_behavior": {
                    "passthrough": "Unmapped input channels pass through 1:1 to output",
                    "ignore": "Unmapped input channels are ignored (output zero)"
                }
            },
            "groups_dmx_input": {
                "title": "Groups with DMX Input Link",
                "description": "Control groups via external DMX input",
                "how_it_works": "Groups can have a 'DMX Input Link' - a master channel that controls the group. When external input changes this master channel, the group triggers and controls all its member channels.",
                "example": {
                    "setup": [
                        "Channel Mapping: Input 1 → Channel 100",
                        "Group: Controls channels 1-5, DMX Input Link = Channel 100"
                    ],
                    "flow": "External Input Ch 1 = 255 → Mapping routes to Ch 100 → Group detects master changed → Group outputs to channels 1-5",
                    "result": "Channels 1-5 output values based on group mode (Proportional or Follow)"
                },
                "group_modes": [
                    {
                        "mode": "Proportional",
                        "description": "Member channels output: base_value × (master_value / 255)"
                    },
                    {
                        "mode": "Follow",
                        "description": "All member channels match the master value exactly"
                    }
                ]
            },
            "input_bypass": {
                "title": "Input Bypass",
                "description": "Temporarily stop input from affecting output",
                "how_it_works": "When bypass is active, external DMX input is still received and may be displayed on the UI, but it is NOT merged into the output. Your local fader values take full control.",
                "use_cases": [
                    "Quick manual override without reconfiguring passthrough",
                    "Temporarily take control during a show",
                    "Testing local values without external interference"
                ],
                "note": "Bypass is session-scoped and resets when the backend restarts"
            },
            "scene_recall_with_input": {
                "title": "Scene Recall with Active Input",
                "description": "How scene recall behaves when external input is active",
                "behaviors": [
                    {
                        "condition": "Bypass OFF, Input Active",
                        "result": "Scene values apply ONLY to channels NOT controlled by input. Input-controlled channels remain at their input values."
                    },
                    {
                        "condition": "Bypass ON",
                        "result": "All scene values apply. Input is temporarily ignored."
                    },
                    {
                        "condition": "No Input Active",
                        "result": "All scene values apply normally."
                    }
                ],
                "example": {
                    "setup": "Input controls channels 1-12, scene has values for all 512 channels",
                    "bypass_off": "Channels 1-12 stay at input values, channels 13-512 change to scene values",
                    "bypass_on": "All 512 channels change to scene values"
                },
                "edge_case": {
                    "title": "Indirect Input Control via Groups",
                    "description": "If a group's master channel is controlled by input, the group's member channels are also considered input-controlled and will be skipped during scene recall.",
                    "example": "Input channels 1-3 are mapped to faders 50-52. A group has its master at channel 50 and controls channels 1-10. During scene recall with bypass OFF, channels 1-10 are skipped because they're indirectly controlled by input through the group."
                },
                "group_faders": {
                    "title": "Group Fader Values in Scenes",
                    "description": "Scenes store group master fader positions. On recall, group masters are restored to their saved positions - unless the group's master channel is controlled by input.",
                    "note": "If a group fader is mapped to a physical input channel, scene recall will skip restoring that group fader (it stays at the input value). After recall, if you move a group fader, it recalculates member channels based on the new master value."
                }
            },
            "loopback_prevention": {
                "title": "Loopback Prevention",
                "description": "When using Art-Net/sACN input and output on the same machine, you may receive your own output packets. Here are ways to prevent this:",
                "options": [
                    {
                        "method": "Different Ports",
                        "description": "Use a non-standard port for input (e.g., 6455 instead of 6454)",
                        "pros": ["Simple to configure"],
                        "cons": ["External source must send to non-standard port"]
                    },
                    {
                        "method": "Different Universes",
                        "description": "Input listens to Art-Net Universe 1, Output sends to Universe 0",
                        "pros": ["Standard ports, no special config on external source"],
                        "cons": ["Must configure universe numbers correctly"]
                    },
                    {
                        "method": "Ignore Self (ignore_self option)",
                        "description": "Automatically filter packets from this machine's IP addresses",
                        "pros": ["Automatic, no manual IP entry needed"],
                        "cons": ["May not work in all network configurations"]
                    },
                    {
                        "method": "Ignore IP (ignore_ip option)",
                        "description": "Manually specify an IP to ignore (e.g., your machine's IP)",
                        "pros": ["Precise control"],
                        "cons": ["Must know and enter the correct IP"]
                    },
                    {
                        "method": "Source IP Filter (source_ip option)",
                        "description": "Only accept packets from a specific external IP",
                        "pros": ["Most secure, only trusted source accepted"],
                        "cons": ["Must know external source IP, only one source allowed"]
                    },
                    {
                        "method": "Unicast Output (Recommended)",
                        "description": "Send output to a specific device IP instead of broadcast. Avoids broadcast permission issues.",
                        "pros": ["No broadcast permission issues", "More efficient network usage", "No loopback interference"],
                        "cons": ["Must know target device IP", "Only works with one target device"]
                    }
                ],
                "recommendation": "For single-device setups, use 'Unicast Output'. For multi-device setups, use 'Different Universes' or enable 'ignore_self'. If you know the external source IP, use 'source_ip' filter for best security."
            },
            "grandmasters": {
                "title": "Grandmasters (Master Faders)",
                "description": "Scale all output values with master faders",
                "types": [
                    {
                        "type": "Global Grandmaster",
                        "description": "Scales ALL output across all universes. Set on the I/O page header.",
                        "formula": "final_output = channel_value × (global_gm / 255)"
                    },
                    {
                        "type": "Universe Grandmaster",
                        "description": "Scales output for a specific universe only. Set per-universe on the I/O page.",
                        "formula": "final_output = channel_value × (universe_gm / 255)"
                    }
                ],
                "combined_formula": "final_output = channel_value × (universe_gm / 255) × (global_gm / 255)",
                "example": {
                    "channel_value": 200,
                    "universe_gm": 200,
                    "global_gm": 128,
                    "calculation": "200 × (200/255) × (128/255) = 200 × 0.78 × 0.50 = 78",
                    "result": "Output: 78"
                },
                "use_cases": [
                    "Global blackout: Set Global GM to 0",
                    "Universe blackout: Set Universe GM to 0 for one universe",
                    "Overall dimming: Reduce Global GM to dim entire show"
                ]
            }
        }
    }
