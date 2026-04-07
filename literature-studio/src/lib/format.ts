export const formatNumber = (value: number | null | undefined): string => {
  if (value === null || value === undefined) {
    return "n/a";
  }

  return new Intl.NumberFormat("en-US").format(value);
};

export const formatCompactNumber = (
  value: number | null | undefined,
): string => {
  if (value === null || value === undefined) {
    return "n/a";
  }

  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
};

export const truncateText = (
  value: string | null | undefined,
  maxLength = 180,
): string => {
  if (!value) {
    return "No summary provided.";
  }

  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength - 1).trimEnd()}...`;
};

export const trimTitle = (value: string, maxLength = 34): string => {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength - 1).trimEnd()}...`;
};

export const splitLines = (value: string): string[] =>
  value
    .split(/[\n,]/g)
    .map((entry) => entry.trim())
    .filter(Boolean);

export const shortId = (value: string, head = 6, tail = 6): string => {
  if (value.length <= head + tail + 3) {
    return value;
  }

  return `${value.slice(0, head)}...${value.slice(-tail)}`;
};

export const formatDate = (value: string | null | undefined): string => {
  if (!value) {
    return "n/a";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
};
