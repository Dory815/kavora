/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.settings;

import java.util.List;
import java.util.Locale;
import java.util.Map;
import net.minecraft.network.chat.Component;
import org.edtp.kavora.NativeRuntime;

/** Display choices belong to the presentation runtime, including menus and non-RTX frames. */
public final class KavoraDisplaySettings {
    public static final String MODE = "rtx.display.hdrMode";
    public static final String PAPER_WHITE = "rtx.display.paperWhiteNits";
    public static final String PEAK = "rtx.display.peakNits";
    static final List<String> KEYS = List.of(MODE, PAPER_WHITE, PEAK);
    private static final String STATUS_PREFIX = "rtx.display.status.";
    private static Status cachedStatus;
    private static long statusTime;

    public enum Mode { OFF, AUTO }
    /** Sodium's read-only enum row supplies a live label without introducing an editable setting. */
    public enum OutputStatus { CURRENT }

    private record Status(String mode, String reason, double paperWhite, double peak) {}

    private KavoraDisplaySettings() {}

    public static boolean available() { return NativeRuntime.isStarted(); }

    static boolean valid(String key, String value) {
        if (key.equals(MODE)) return value.equals("0") || value.equals("1");
        if (!key.equals(PAPER_WHITE) && !key.equals(PEAK)) return false;
        try {
            double nits = Double.parseDouble(value);
            return Double.isFinite(nits) && (nits == 0 || (key.equals(PAPER_WHITE)
                    ? nits >= 80 && nits <= 500 : nits >= 200 && nits <= 10000));
        } catch (NumberFormatException invalid) {
            return false;
        }
    }

    static void apply(Map<String, String> values) {
        if (!available()) return;
        for (String key : KEYS) {
            if (values.containsKey(key)) NativeRuntime.api().setConfigVariable(key, values.get(key));
        }
        cachedStatus = null;
    }

    static Mode mode() { return "0".equals(KavoraVideoSettings.displayValue(MODE, "1")) ? Mode.OFF : Mode.AUTO; }
    static void stageMode(Mode mode) { KavoraVideoSettings.stage(MODE, mode == Mode.AUTO ? "1" : "0"); }

    static int nitsPosition(String key, int minimum, int step) {
        double value = Double.parseDouble(KavoraVideoSettings.displayValue(key, "0"));
        return value == 0 ? 0 : 1 + (int) Math.round((value - minimum) / step);
    }

    static int nitsValue(int position, int minimum, int step) {
        return position == 0 ? 0 : minimum + (position - 1) * step;
    }

    static void stageNits(String key, int position, int minimum, int step) {
        KavoraVideoSettings.stage(key, Integer.toString(nitsValue(position, minimum, step)));
    }

    static Component nitsText(int position, int minimum, int step) {
        return position == 0 ? text("auto") : Component.translatable("kavora.display.nits", nitsValue(position, minimum, step));
    }

    static Component modeText(Mode value) { return text(value.name().toLowerCase(Locale.ROOT)); }
    static Component outputText() { return text("output." + status().mode()); }

    static Component statusText() {
        Status status = status();
        return Component.translatable("kavora.display.status.tip", text("output." + status.mode()),
                text("reason." + status.reason()), Math.round(status.paperWhite()), Math.round(status.peak()));
    }

    private static Status status() {
        long now = System.nanoTime();
        if (cachedStatus == null || now - statusTime >= 1_000_000_000L) {
            cachedStatus = queryStatus();
            statusTime = now;
        }
        return cachedStatus;
    }

    private static Status queryStatus() {
        if (!available()) return new Status("sdr", "pending", 80, 80);
        try {
            var api = NativeRuntime.api();
            String mode = api.getConfigVariableResolved(STATUS_PREFIX + "mode");
            String reason = api.getConfigVariableResolved(STATUS_PREFIX + "reason");
            double white = Double.parseDouble(api.getConfigVariableResolved(STATUS_PREFIX + "paperWhiteNits"));
            double peak = Double.parseDouble(api.getConfigVariableResolved(STATUS_PREFIX + "peakNits"));
            if (!Double.isFinite(white) || !Double.isFinite(peak) || white <= 0 || peak < white) {
                return new Status("sdr", "query-failed", 80, 80);
            }
            reason = switch (reason) {
                case "off", "legacy-client", "no-window", "query-failed", "os-hdr-disabled",
                        "colorspace-extension-unavailable", "hdr-surface-unavailable", "swapchain-failed", "pending", "active" -> reason;
                default -> "query-failed";
            };
            return new Status(mode.equals("hdr10") ? "hdr10" : "sdr", reason, white, peak);
        } catch (RuntimeException unavailable) {
            return new Status("sdr", "query-failed", 80, 80);
        }
    }

    private static Component text(String key) { return Component.translatable("kavora.display." + key); }
}
