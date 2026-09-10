#!/usr/bin/env python3
"""Append synthetic touch input_event structs to a device stub file.

Usage:
    inject.py press <x> <y> <event-file>   # press at RAW coords (see docs/TOUCH.md)
    inject.py release  x   x  <event-file> # release (coords ignored)

Press and release are SEPARATE calls on purpose: the LVGL read-cb drains all queued
events per poll, so a press must be sampled (sleep ~1s) before the release, else only
the net (released) state is seen. Coordinates are RAW touch coords (180deg-flipped from
what you see) — scripts/30_tap.sh does the flip for you.
"""
import struct,sys
def ev(t,c,v): return struct.pack('<iiHHi',0,0,t,c,v)
EV_SYN,EV_KEY,EV_ABS=0,1,3
SYN_REPORT=0; BTN_TOUCH=0x14a
ABS_X,ABS_Y=0,1
ABS_MT_TRACKING_ID,ABS_MT_POSITION_X,ABS_MT_POSITION_Y=0x39,0x35,0x36
mode=sys.argv[1]; path=sys.argv[-1]
buf=b''
if mode=='press':
    x=int(sys.argv[2]); y=int(sys.argv[3])
    buf+=ev(EV_ABS,ABS_MT_TRACKING_ID,0)      # id=0 -> pressed
    buf+=ev(EV_ABS,ABS_MT_POSITION_X,x)
    buf+=ev(EV_ABS,ABS_MT_POSITION_Y,y)
    buf+=ev(EV_ABS,ABS_X,x); buf+=ev(EV_ABS,ABS_Y,y)
    buf+=ev(EV_KEY,BTN_TOUCH,1)               # also pressed
    buf+=ev(EV_SYN,SYN_REPORT,0)
elif mode=='release':
    buf+=ev(EV_ABS,ABS_MT_TRACKING_ID,-1)     # id=-1 -> released
    buf+=ev(EV_KEY,BTN_TOUCH,0)
    buf+=ev(EV_SYN,SYN_REPORT,0)
open(path,'ab').write(buf)
print("  %s %s -> %d events"%(mode, sys.argv[2:4] if mode=='press' else '', len(buf)//16))
