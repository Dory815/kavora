/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.render;

/** Monotonic completion of scene submissions on the render thread. */
public interface SceneCompletion {
    long submittedScene();
    long completedScene();
}
