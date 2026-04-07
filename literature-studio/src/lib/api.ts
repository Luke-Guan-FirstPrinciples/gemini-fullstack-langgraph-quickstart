const stringifyDetail = (detail: unknown): string => {
  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail.map(stringifyDetail).join(", ");
  }

  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return "Unexpected error payload.";
    }
  }

  return "Unexpected error payload.";
};

const extractErrorMessage = (
  payload: unknown,
  fallback: string,
): string => {
  if (payload && typeof payload === "object") {
    const objectPayload = payload as Record<string, unknown>;

    for (const key of ["detail", "message", "error"]) {
      const value = objectPayload[key];
      if (value !== undefined) {
        return stringifyDetail(value);
      }
    }
  }

  if (typeof payload === "string" && payload.trim().length > 0) {
    return payload;
  }

  return fallback;
};

export async function requestJson<T>(
  input: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;

  try {
    response = await fetch(input, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Network request failed.";
    throw new Error(message);
  }

  const text = await response.text();
  const fallbackMessage = `${response.status} ${response.statusText}`.trim();

  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    throw new Error(extractErrorMessage(payload, fallbackMessage));
  }

  return payload as T;
}
