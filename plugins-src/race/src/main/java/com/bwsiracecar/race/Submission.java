package com.bwsiracecar.race;

import java.util.List;
import java.util.UUID;

/** What the plugin writes into the queue and reads back out of the results. */
public class Submission {

    public enum State { QUEUED, SIMULATING, REPLAYING, RECORDED }

    /** The queue file, minus the .json suffix, is the id. */
    public static final class Payload {
        public String id;
        public String player_uuid;
        public String player_name;
        public double submitted_at;
        public String code;
    }

    /** What the host-side runner writes back. */
    public static final class Result {
        public String id;
        public String player_uuid;
        public String player_name;
        public String status;
        public String error;
        public Double time_s;
        public List<List<Double>> trajectory;

        public boolean ok() {
            return "ok".equals(status) && time_s != null
                    && trajectory != null && !trajectory.isEmpty();
        }

        public UUID uuid() {
            return UUID.fromString(player_uuid);
        }
    }
}
