import ldeApi from "./ldeApi";

/** One selectable target data format from LDE `/available-data-formats`. */
export interface DataFormat {
  name: string;
  version: string;
  contributorOrganization: string;
  TransformationVersions: string[];
}

export interface AvailableDataFormats {
  metadata: Record<string, unknown>;
  DataFormats: DataFormat[];
}

export interface ExportParams {
  learnerId: string;
  dataModelName: string;
  dataModelVersion: string;
  dataModelContributorOrganization: string;
}

class ExportService {
  /** List the target data formats this deployment can export to. */
  async getAvailableDataFormats(): Promise<AvailableDataFormats> {
    const response = await ldeApi.get<AvailableDataFormats>("/available-data-formats");
    return response.data;
  }

  /** Export a learner's data in the selected format. Returns the raw document
   * (LDE `/exports` responds with a format-dependent JSON object). */
  async runExport(params: ExportParams): Promise<unknown> {
    const response = await ldeApi.get<unknown>("/exports", {
      params: {
        learnerId: params.learnerId,
        dataModelName: params.dataModelName,
        dataModelVersion: params.dataModelVersion,
        dataModelContributorOrganization: params.dataModelContributorOrganization,
      },
    });
    return response.data;
  }
}

export default new ExportService();
