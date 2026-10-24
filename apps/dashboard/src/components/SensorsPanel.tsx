import type { DataQualityResponse, SensorsResponse } from "../types/api";
import type { SliceError } from "../hooks/useDashboardData";
import { formatLahoreWithOriginal } from "../utils/time";
import { StateBlock } from "./StateBlock";

interface SensorsPanelProps {
  sensors: SensorsResponse | null;
  quality: DataQualityResponse | null;
  sensorsError?: SliceError;
  qualityError?: SliceError;
  loading?: boolean;
}

export function SensorsPanel({
  sensors,
  quality,
  sensorsError,
  qualityError,
  loading,
}: SensorsPanelProps) {
  return (
    <section className="sensors-panel panel rise rise-delay-3">
      <header className="chart-panel__head">
        <div>
          <h2>Sensors &amp; status</h2>
          <p>Station inventory and data-quality snapshot from the API.</p>
        </div>
      </header>

      <div className="sensors-panel__grid">
        <div>
          <h3 className="sensors-panel__title">Stations</h3>
          {loading && !sensors ? (
            <div className="skeleton" style={{ height: 120 }} />
          ) : sensorsError && !sensors ? (
            <StateBlock
              title={
                sensorsError.kind === "network"
                  ? "Network failure"
                  : "Sensors API error"
              }
              message={sensorsError.message}
              tone="danger"
            />
          ) : !sensors || sensors.count === 0 ? (
            <StateBlock
              title="No sensors reported"
              message="The sensors endpoint returned an empty list."
            />
          ) : (
            <ul className="sensor-list">
              {sensors.sensors.map((s) => {
                const last = formatLahoreWithOriginal(s.last_observed_at);
                return (
                  <li key={s.station_id}>
                    <div>
                      <strong>{s.station_id}</strong>
                      <span>{s.location_name ?? "Unnamed location"}</span>
                    </div>
                    <div className="sensor-list__meta">
                      <span>{s.source_name ?? "source n/a"}</span>
                      <span title={last.title}>
                        {last.display}
                        {last.display !== "—" ? " Lahore" : ""}
                      </span>
                      {s.observation_count != null ? (
                        <span>{s.observation_count} obs</span>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div>
          <h3 className="sensors-panel__title">Data quality</h3>
          {loading && !quality ? (
            <div className="skeleton" style={{ height: 120 }} />
          ) : qualityError && !quality ? (
            <StateBlock
              title={
                qualityError.kind === "network"
                  ? "Network failure"
                  : "Data-quality API error"
              }
              message={qualityError.message}
              tone="warning"
            />
          ) : !quality ? (
            <StateBlock
              title="No quality report"
              message="Quality endpoint returned no payload."
            />
          ) : (
            <div className="quality-grid">
              <div>
                <span>Database</span>
                <strong className={quality.database_healthy ? "ok" : "bad"}>
                  {quality.database_healthy ? "Healthy" : "Degraded"}
                </strong>
              </div>
              <div>
                <span>Valid</span>
                <strong>{quality.class_counts.valid}</strong>
              </div>
              <div>
                <span>Suspect</span>
                <strong>{quality.class_counts.suspect}</strong>
              </div>
              <div>
                <span>Invalid</span>
                <strong>{quality.class_counts.invalid}</strong>
              </div>
              {quality.inactive_stations.length > 0 ? (
                <p className="quality-note">
                  Inactive: {quality.inactive_stations.join(", ")}
                </p>
              ) : (
                <p className="quality-note">No inactive stations flagged.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
