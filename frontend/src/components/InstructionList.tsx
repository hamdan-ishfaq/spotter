import {
  List,
  ListItemButton,
  ListItemText,
  Chip,
  Stack,
  Typography,
  Paper,
} from "@mui/material";

export type Instruction = {
  seq: number;
  action: string;
  text: string;
  start: string;
  end: string;
  status: string;
  location_label: string;
  lat?: number | null;
  lng?: number | null;
};

type Props = {
  items: Instruction[];
  selectedSeq?: number | null;
  onSelect?: (item: Instruction) => void;
};

export function InstructionList({ items, selectedSeq, onSelect }: Props) {
  return (
    <Paper variant="outlined" sx={{ maxHeight: { xs: 280, md: 420 }, overflow: "auto", bgcolor: "background.paper" }}>
      <Typography variant="subtitle1" sx={{ px: 2, pt: 1.5, fontWeight: 650 }}>
        Route instructions
      </Typography>
      <List dense>
        {items.map((item) => (
          <ListItemButton
            key={item.seq}
            selected={selectedSeq === item.seq}
            onClick={() => onSelect?.(item)}
            alignItems="flex-start"
          >
            <ListItemText
              primary={
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <Chip size="small" label={item.action} />
                  <Typography variant="body2">{item.text}</Typography>
                </Stack>
              }
              secondary={`${formatTime(item.start)} → ${formatTime(item.end)}`}
            />
          </ListItemButton>
        ))}
      </List>
    </Paper>
  );
}

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
