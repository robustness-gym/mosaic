export async function get(url: string): Promise<any> {
    const res: Response = await fetch(url);
    if (!res.ok) {
        throw new Error('HTTP status ' + res.status);
    }
    const json = await res.json();
    return json;
}

export async function post(url: string, data: any): Promise<any> {
    const res: Response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        throw new Error(
            "HTTP status " + res.status + ": " + res.statusText + "\n url: " + url + "\n data: " + JSON.stringify(data)
        );
    }
    const json = await res.json();
    return json;
}