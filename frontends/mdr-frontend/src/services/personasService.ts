import api from "./api";

/** A curated demo learner, served from the shared demo-persona source (#1055). */
export interface Persona {
  username: string;
  firstname: string;
  lastname: string;
  identifier: string;
  identifier_type: string;
  identifier_type_enum: string;
}

class PersonasService {
  /** Fetch the curated demo learners.
   *
   * Served from the shared `demo_personas` brick (#1055) via `GET /demo/personas`
   * on the MDR API — the single source that the Advisor app also uses, so the
   * playground's picker can't drift. (Endpoint is the browser-delivery companion
   * to #1055.)
   */
  async getPersonas(): Promise<Persona[]> {
    const response = await api.get<Persona[]>("/demo/personas");
    return response.data;
  }
}

export default new PersonasService();
