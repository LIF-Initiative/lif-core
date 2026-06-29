import axios from 'axios';

const API_URL = import.meta.env.VITE_LIF_ADVISOR_API_URL;

const axiosInstance = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

axiosInstance.interceptors.request.use(
    (config) => {
        const accessToken = localStorage.getItem('token');
        if (accessToken) {
            config.headers.Authorization = `Bearer ${accessToken}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

axiosInstance.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        if (error.response?.status === 401 && !originalRequest?._retry) {
            originalRequest._retry = true;

            try {
                const refreshToken = localStorage.getItem('refreshToken');
                const response = await axiosInstance.post('/refresh-token', { 'refresh_token': refreshToken });

                localStorage.setItem('token', response.data.access_token);

                // Retry the original request with the new token
                originalRequest.headers.Authorization = `Bearer ${response.data.access_token}`;
                return axiosInstance(originalRequest);
            } catch (error) {
                localStorage.removeItem('token');
                localStorage.removeItem('refreshToken');
                window.location.href = '/login';
            }
        }

        return Promise.reject(error);
    }
);


export default axiosInstance;
