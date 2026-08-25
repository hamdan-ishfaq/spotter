import { createTheme } from "@mui/material/styles";

/** Freight-ops theme — avoid generic purple SaaS look. */
export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#1B3A4B" },
    secondary: { main: "#C45C26" },
    background: { default: "#F3F1EC", paper: "#FFFdf8" },
    text: { primary: "#15202B", secondary: "#5C6B73" },
  },
  typography: {
    fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
    h1: { fontFamily: '"Source Serif 4", Georgia, serif', fontWeight: 650 },
    h2: { fontFamily: '"Source Serif 4", Georgia, serif', fontWeight: 650 },
    h3: { fontFamily: '"Source Serif 4", Georgia, serif', fontWeight: 600 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  shape: { borderRadius: 10 },
});
