#include "mod_plugins.h"

/*
 * Ape Escape's projection, culling, UI, and dome hooks remain framework
 * configuration. These trusted activation callbacks let the game-owned mod
 * package choose how those hooks are presented before renderer startup.
 */
static void ape_widescreen_16_9_activate(void) {
    (void)psx_mod_set_fixed_display_aspect(16u, 9u);
}

static void ape_widescreen_21_9_activate(void) {
    (void)psx_mod_set_fixed_display_aspect(21u, 9u);
}

static void ape_widescreen_adaptive_activate(void) {
    (void)psx_mod_set_fixed_display_aspect(16u, 9u);
    (void)psx_mod_set_adaptive_display_aspect(21u, 9u);
}

PSX_MOD_CONSTRUCTOR(ape_register_widescreen_plugins) {
    (void)psx_mod_register_activation_plugin(
        "ape.widescreen.16-9", ape_widescreen_16_9_activate);
    (void)psx_mod_register_activation_plugin(
        "ape.widescreen.21-9", ape_widescreen_21_9_activate);
    (void)psx_mod_register_activation_plugin(
        "ape.widescreen.adaptive", ape_widescreen_adaptive_activate);
}
