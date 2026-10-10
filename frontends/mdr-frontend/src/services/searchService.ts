import api from "./api";

const apiBaseUrl = import.meta.env.VITE_API_URL;
interface ApiResponse<T> {
    data: T;
}

interface OptionalSearchParams {
    data_model_id?: number;
    contributor_organization?: string;
    only_extension?: boolean;
    only_base?: boolean;
}

export interface SearchResults {
    attributes: any[];
    data_models: any[];
    entities: any[];
    transformation_groups: any[];
    transformations: any[];
    value_set_values: any[];
    value_sets: any[];
}

export const searchAll = async (query: string, options: OptionalSearchParams = {}) => {
    try {
        let url = `${apiBaseUrl}/search/?search_key=${query}`;
        // for each key in optional params add another query param if it exists
        for (const key in options) {
            if (options[key as keyof OptionalSearchParams]) {
                url += `&${key}=${options[key as keyof OptionalSearchParams]}`;
            }
        }
        const result = await api.get<ApiResponse<SearchResults>>(url);
        return result.data;
    } catch (error) {
        console.error('Error fetching data:', error);
    }
};
