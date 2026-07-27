#include "mod_plugins.h"

/*
 * Keep the host switch behind Ape Escape's trusted mod catalog. The game
 * still owns movie teardown; this enables the runtime's existing accelerated,
 * muted playback path without exposing a second Settings control.
 */
static void ape_skip_fmvs_activate(void) {
    (void)psx_mod_set_auto_skip_fmv(1);
}

PSX_MOD_CONSTRUCTOR(ape_register_skip_fmv_plugin) {
    (void)psx_mod_register_activation_plugin(
        "ape.fmv.skip", ape_skip_fmvs_activate);
}
