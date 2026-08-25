import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Container,
  Grid,
  Paper,
  Stack,
  Tab,
  Tabs,
  Typography,
  Chip,
  Snackbar,
} from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import PrintIcon from "@mui/icons-material/Print";
import RefreshIcon from "@mui/icons-material/Refresh";
import { TripForm } from "./components/TripForm";
import { RouteMap } from "./components/RouteMap";
import { InstructionList, type Instruction } from "./components/InstructionList";
import { DailyLogSheet, type DailyLog } from "./components/DailyLogSheet";
import { ApiError, healthCheck, planTrip } from "./api/client";
import type { PlanRequest, PlanResponse } from "./api/types";
import { buildShareUrl, planToSearchParams, readPlanFromLocation } from "./shareUrl";
import { API_BASE_URL } from "./constants";

type ApiState = "waking" | "ready" | "down";

const isHosted =
  !API_BASE_URL.includes("127.0.0.1") && !API_BASE_URL.includes("localhost");

export default function App() {
  const initialFromUrl = useMemo(() => readPlanFromLocation(), []);
  const autoPlanRef = useRef(Boolean(initialFromUrl));

  const [apiReady, setApiReady] = useState<ApiState>("waking");
  const [wakeAttempt, setWakeAttempt] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [lastRequest, setLastRequest] = useState<PlanRequest | null>(initialFromUrl);
  const [logTab, setLogTab] = useState(0);
  const [selected, setSelected] = useState<Instruction | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const wakeApi = useCallback(async () => {
    setApiReady("waking");
    setWakeAttempt((n) => n + 1);
    const ok = await healthCheck();
    setApiReady(ok ? "ready" : "down");
    return ok;
  }, []);

  useEffect(() => {
    void wakeApi();
  }, [wakeApi]);

  const onSubmit = useCallback(
    async (body: PlanRequest) => {
      setLoading(true);
      setError(null);
      setSelected(null);
      setLastRequest(body);

      const params = planToSearchParams(body);
      const nextUrl = `${window.location.pathname}?${params.toString()}`;
      window.history.replaceState(null, "", nextUrl);

      try {
        if (apiReady !== "ready") {
          const ok = await wakeApi();
          if (!ok) {
            throw new ApiError(
              "API_UNAVAILABLE",
              "API is still waking up. Wait ~60s and try again, or click Retry connection.",
            );
          }
        }
        const result = await planTrip(body);
        setPlan(result);
        setLogTab(0);
      } catch (e) {
        const msg =
          e instanceof ApiError ? `${e.code}: ${e.message}` : "Plan failed";
        setError(msg);
      } finally {
        setLoading(false);
      }
    },
    [apiReady, wakeApi],
  );

  useEffect(() => {
    if (!initialFromUrl || !autoPlanRef.current) {
      return;
    }
    autoPlanRef.current = false;
    if (apiReady === "ready") {
      void onSubmit(initialFromUrl);
    }
  }, [apiReady, initialFromUrl, onSubmit]);

  async function copyShareLink() {
    if (!lastRequest) {
      return;
    }
    const url = buildShareUrl(lastRequest);
    try {
      await navigator.clipboard.writeText(url);
      setToast("Share link copied — opens this trip in the app.");
    } catch {
      setToast(url);
    }
  }

  const geometry = useMemo(() => {
    return (plan?.route?.geometry || []) as [number, number][];
  }, [plan]);

  const instructions = (plan?.instructions || []) as Instruction[];
  const dailyLogs = (plan?.daily_logs || []) as DailyLog[];
  const summary = plan?.summary || {};

  return (
    <Box
      sx={{
        minHeight: "100vh",
        background:
          "linear-gradient(165deg, #E8EEF1 0%, #F3F1EC 45%, #EDE6DC 100%)",
        pb: 6,
      }}
    >
      <Container maxWidth="lg" sx={{ py: 4 }} className="no-print">
        <Typography
          variant="h1"
          sx={{ fontSize: { xs: "2rem", md: "2.6rem" }, mb: 0.5 }}
        >
          Spotter HOS Planner
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 3, maxWidth: 720 }}>
          Plan a property-carrying trip under 70h/8-day HOS rules — map, route
          instructions, and drawn daily logs.
        </Typography>

        {apiReady === "waking" && (
          <Alert severity="info" sx={{ mb: 2 }}>
            Starting API{isHosted ? " on Render Free" : ""} — first load may take
            up to ~60s while the server wakes{wakeAttempt > 1 ? " (retrying…)" : ""}.
          </Alert>
        )}
        {apiReady === "down" && (
          <Alert
            severity="warning"
            sx={{ mb: 2 }}
            action={
              <Button
                color="inherit"
                size="small"
                startIcon={<RefreshIcon />}
                onClick={() => void wakeApi()}
              >
                Retry
              </Button>
            }
          >
            {isHosted ? (
              <>
                API not reachable at <code>{API_BASE_URL}</code>. Render Free
                sleeps after idle — click Retry or wait a minute.
              </>
            ) : (
              <>
                API not reachable at <code>{API_BASE_URL}</code>. Start Django:{" "}
                <code>python manage.py runserver 127.0.0.1:8080</code>.
              </>
            )}
          </Alert>
        )}

        <Paper sx={{ p: 3, mb: 3 }} elevation={0} variant="outlined">
          <TripForm
            loading={loading}
            onSubmit={onSubmit}
            initial={initialFromUrl ?? undefined}
          />
          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
        </Paper>
      </Container>

      {plan && (
        <Container maxWidth="lg">
          <Alert severity="info" sx={{ mb: 2 }} className="no-print">
            <strong>Assumptions:</strong> {(plan.assumptions || []).join(" · ")}
          </Alert>

          <Stack
            direction="row"
            spacing={1}
            sx={{ mb: 2, flexWrap: "wrap", gap: 1 }}
            className="no-print"
          >
            <Chip label={`${summary.total_miles ?? "—"} mi`} />
            <Chip label={`${summary.total_driving_hours ?? "—"} h drive`} />
            <Chip label={`${summary.total_on_duty_hours ?? "—"} h on-duty`} />
            <Chip label={`${summary.days ?? "—"} day(s)`} />
            <Chip label={`Cycle rem. ${summary.cycle_remaining_end ?? "—"} h`} />
            {summary.inserted_34h_restart ? (
              <Chip color="secondary" label="34h restart used" />
            ) : null}
            <Button
              size="small"
              variant="outlined"
              startIcon={<ContentCopyIcon />}
              onClick={() => void copyShareLink()}
            >
              Copy share link
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<PrintIcon />}
              onClick={() => window.print()}
            >
              Print logs
            </Button>
          </Stack>

          <Grid container spacing={2} className="no-print" sx={{ mb: 3 }}>
            <Grid size={{ xs: 12, md: 7 }}>
              <RouteMap
                geometry={geometry}
                stops={(plan.route?.stops || []) as never[]}
                highlight={
                  selected?.lat != null && selected?.lng != null
                    ? { lat: selected.lat, lng: selected.lng }
                    : null
                }
              />
            </Grid>
            <Grid size={{ xs: 12, md: 5 }}>
              <InstructionList
                items={instructions}
                selectedSeq={selected?.seq}
                onSelect={setSelected}
              />
            </Grid>
          </Grid>

          <Typography
            variant="h3"
            sx={{ fontSize: "1.4rem", mb: 1, fontWeight: 600 }}
            className="no-print"
          >
            Daily log sheets
          </Typography>
          <Typography
            color="text.secondary"
            sx={{ mb: 2, maxWidth: 640, fontSize: "0.95rem" }}
            className="no-print"
          >
            FMCSA-style 24-hour grids with duty line, totals, and location remarks — use Print logs for a clean PDF.
          </Typography>
          <Tabs
            value={logTab}
            onChange={(_, v) => setLogTab(v)}
            sx={{
              mb: 2,
              "& .MuiTab-root": { fontWeight: 500, textTransform: "none" },
            }}
            className="no-print"
            variant="scrollable"
          >
            {dailyLogs.map((log, i) => (
              <Tab key={log.date} label={`Day ${i + 1} · ${log.date}`} />
            ))}
          </Tabs>
          {dailyLogs.map((log, i) => (
            <Box
              key={log.date}
              className="daily-log-print-page"
              sx={{
                display: logTab === i ? "block" : "none",
                "@media print": { display: "block !important" },
              }}
            >
              <DailyLogSheet log={log} />
            </Box>
          ))}
        </Container>
      )}

      <Snackbar
        open={Boolean(toast)}
        autoHideDuration={5000}
        onClose={() => setToast(null)}
        message={toast}
        className="no-print"
      />
    </Box>
  );
}
