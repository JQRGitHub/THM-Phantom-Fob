# Phantom Fob — Companion Code

This repository accompanies the **Phantom Fob** CAN CTF writeup.

The challenge involved a web-based vehicle instrument cluster, a virtual key fob, and a simulated CAN bus exposed through socketcand.

The included scripts document the analysis workflow used to identify the vehicle-state and fob-command frames, study freshness/replay behavior, recover the checksum relationship, and demonstrate forging a **known** valid command.

## 

## Files

* Phantom\_Fob\_CTF\_Writeup.pdf — polished technical writeup.
* watch\_can.py — connects to socketcand and displays raw CAN frames, optionally filtering by CAN ID.
* capture\_fob.py — correlates legitimate /press actions with nearby CAN traffic to identify quiet command/state frames.
* race.py — races legitimate web controls to expose shared freshness values and make the checksum relationship easier to spot.
* forge\_demo.py — demonstrates forging a **known** IMMOB\_ARM command using freshly observed rolling/freshness state and the recovered checksum formula.

## 

## Requirements

All scripts use only the Python 3 standard library.

The target environment must expose:

* the challenge web application (default 8080/tcp), and socketcand (default 29536/tcp).

The scripts assume the CAN interface is vcan0 unless overridden.

## 

## Example Usage

Watch all CAN traffic: python3 watch\_can.py <TARGET\_IP>

Watch only selected IDs: python3 watch\_can.py <TARGET\_IP> --ids 12A,429

Correlate legitimate fob presses with CAN frames: python3 capture\_fob.py <TARGET\_IP>

Run the concurrency experiment after identifying the fob CAN ID: python3 race.py <TARGET\_IP> --fob-id 12A

Demonstrate forging a known valid immobiliser-arm command: python3 forge\_demo.py <TARGET\_IP> --fob-id 12A --state-id 429




## Recovered Checksum Relationship

For the instance documented in the writeup, the fob frame followed this general structure:

Byte 0   rolling counter
Byte 1   command opcode
Byte 2   freshness value A
Byte 3   constant
Byte 4   8-bit additive checksum
Byte 5   freshness value B
Byte 6   constant
Byte 7   constant


The checksum was recovered as: checksum = (counter + command + freshness\_A + freshness\_B + 0x20) \& 0xff
Challenge instances may randomize arbitration IDs and other values, so the IDs shown in the writeup should be treated as examples rather than universal constants.

## Scope / Ethics

These scripts were created for an authorized CTF environment. They are provided for education, reproducibility, and challenge writeup support. Do not use them against systems you do not own or have explicit permission to test.

## 

