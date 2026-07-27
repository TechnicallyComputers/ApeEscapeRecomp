Ape Escape Interpolated Frame Rate (Experimental)

This mod leaves Ape Escape's executable, VSync waits, simulation, timers, and
audio untouched. It blends the two most recent completed game frames in
PSXrecomp's OpenGL presentation path at 60, 120, 144, 165, or Uncapped.

The interpolation is a presentation-only crossfade, not motion-vector
generation. It may show blending/ghosting around fast-moving objects. Uncapped
presents as quickly as the GPU and window system allow and may use substantial
CPU/GPU resources.
