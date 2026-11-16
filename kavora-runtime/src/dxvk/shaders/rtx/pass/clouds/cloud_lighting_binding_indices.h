// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
#pragma once

#include "rtx/pass/common_binding_indices.h"

#define CLOUD_LIGHTING_BINDING_OUTPUT 40

#if CLOUD_LIGHTING_BINDING_OUTPUT <= COMMON_MAX_BINDING
#error "Cloud lighting bindings overlap common bindings."
#endif
