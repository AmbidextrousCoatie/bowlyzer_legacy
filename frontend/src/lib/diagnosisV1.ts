import type { DataOdditiesPayload, DataOddityType, WeekMatrixPayload } from "../hooks/useLeague";
import { fetchV1 } from "./v1";

export async function loadWeekMatrix(): Promise<WeekMatrixPayload> {
  return fetchV1<WeekMatrixPayload>("/api/v1/diagnosis/week-matrix");
}

export async function loadOddities(
  types: DataOddityType[],
  limit?: number,
): Promise<DataOdditiesPayload> {
  return fetchV1<DataOdditiesPayload>("/api/v1/diagnosis/oddities", {
    types: types.length > 0 ? types.join(",") : undefined,
    limit,
  });
}
