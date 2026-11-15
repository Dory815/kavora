/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: LGPL-3.0-only
 */
package org.edtp.kavora.horizon;

import org.edtp.kavora.render.SceneCompletion;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class TerrainSubmissionTest {
    private static final class Timeline implements SceneCompletion {
        long submitted, completed;
        public long submittedScene() { return submitted; }
        public long completedScene() { return completed; }
    }

    @Test
    void queuedUploadsReleaseCreditsAtCompletionAndMayPublishInQueueOrder() {
        var timeline = new Timeline();
        var submission = new TerrainSubmission(512);
        submission.begin(timeline, 1, 0);
        long staged = submission.scene();
        assertTrue(submission.upload(253));
        assertTrue(submission.retire(512));
        submission.finish();
        assertFalse(submission.submitted(staged));

        timeline.submitted++;
        submission.begin(timeline, 2, 0);
        assertTrue(submission.submitted(staged));
        long stagedLater = submission.scene();
        assertTrue(submission.upload(256));
        assertFalse(submission.retire(1));
        submission.finish();

        timeline.submitted++;
        submission.begin(timeline, 3, 0);
        assertTrue(submission.submitted(stagedLater));
        assertFalse(submission.upload(1));
        assertTrue(submission.operation());
        submission.finish();

        timeline.completed = staged;
        submission.begin(timeline, 4, 0);
        assertEquals(256, submission.inFlight());
        assertTrue(submission.upload(256));
        assertFalse(submission.upload(1));
        assertTrue(submission.retire(512));
    }
}
