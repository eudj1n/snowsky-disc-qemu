# Observe output-route selection live. ctx = *(0x832214); ctx+0x58 = out device (6=I2S3_OUT).
set pagination off
set confirm off
break *0x0047670c
commands
  silent
  printf "[probe] get_i2s3_pcm_device: card discovery runs\n"
  continue
end
break *0x00474f84
commands
  silent
  set $c = *(unsigned int *)0x832214
  printf "[probe] set_out_device enter: ctx=0x%x out_dev_before=%d\n", $c, $c?*(int*)($c+0x58):-999
  continue
end
break *0x00471e10
commands
  silent
  set $c = *(unsigned int *)0x832214
  printf "[probe] at pcm_open call: out_dev=%d (6=I2S3_OUT)  hw:%d,%d\n", $c?*(int*)($c+0x58):-999, $a0, $a1
  continue
end
continue
