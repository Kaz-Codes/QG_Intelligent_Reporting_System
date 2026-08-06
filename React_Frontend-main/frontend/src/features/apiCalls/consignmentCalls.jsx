export const callApi = async(type, url, body, params)=>{
    try {
        let response

        if (type == "post"){
            response = await axios.post(url, body, {withCredentials:true})
        }
        if (type == "put") {
            response = await axios.put(url, body, { withCredentials: true })
        }
        if (type == "delete") {
            response = await axios.delete(url, { withCredentials: true })
        }
        if (type == "get") {
            response = await axios.get(url, { 
                params,
                withCredentials: true 
            })
        }

        const data = response.data.data
        console.log(data)

        return data
    } catch (error) {
        if (axios.isAxiosError(error)) {
            console.log(error.response?.data);
        }
    }
}