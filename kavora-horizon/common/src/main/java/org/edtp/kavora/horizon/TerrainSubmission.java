/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: LGPL-3.0-only
 */
package org.edtp.kavora.horizon;

import org.edtp.kavora.render.SceneCompletion;

import java.util.ArrayDeque;

/** Tracks staging credits until Vulkan has finished with the corresponding scene. */
final class TerrainSubmission {
    private record Flight(long scene, long uploads, long retirements) {}
    private final ArrayDeque<Flight> flights = new ArrayDeque<>();
    private final long capacity;
    private long submitted, frameStart, idleFrameNs, allowanceNs;
    private long inFlight, retiring, uploads, retirements;
    private int operations;

    TerrainSubmission(long capacity) {
        this.capacity = capacity;
    }

    void begin(SceneCompletion completion, long now, long targetFrameNs) {
        long previousScene = submitted;
        submitted = completion.submittedScene();
        if (frameStart != 0 && submitted == previousScene + 1) {
            long period = now - frameStart;
            if (operations == 0) idleFrameNs = idleFrameNs == 0 ? period : (3 * idleFrameNs + period) / 4;
        }
        // The completion queue paces uploads when there is no observable spare frame time.
        allowanceNs = idleFrameNs > 0 && idleFrameNs < targetFrameNs
                ? targetFrameNs - idleFrameNs : Long.MAX_VALUE;
        frameStart = now;
        uploads = retirements = 0;
        operations = 0;
        if (!flights.isEmpty()) {
            long completed = completion.completedScene();
            while (!flights.isEmpty() && flights.getFirst().scene <= completed) {
                Flight flight = flights.removeFirst();
                inFlight -= flight.uploads;
                retiring -= flight.retirements;
            }
        }
    }

    boolean upload(long bytes) {
        // Native staging buffers are cache-line aligned.
        long allocation = (bytes + 63) & ~63L;
        if (allocation > capacity - inFlight - uploads || !operation()) return false;
        uploads += allocation;
        return true;
    }

    boolean retire(long bytes) {
        if (bytes > capacity - retiring - retirements || !operation()) return false;
        retirements += bytes;
        return true;
    }

    boolean operation() {
        if (allowanceNs != Long.MAX_VALUE && operations >= TerrainMeshStream.BATCH_PAGES
                && System.nanoTime() - frameStart >= allowanceNs) return false;
        operations++;
        return true;
    }

    void finish() {
        if (uploads == 0 && retirements == 0) return;
        flights.addLast(new Flight(scene(), uploads, retirements));
        inFlight += uploads;
        retiring += retirements;
        uploads = retirements = 0;
    }

    long inFlight() { return inFlight + uploads; }
    long scene() { return submitted + 1; }
    boolean submitted(long scene) { return submitted >= scene; }
}
