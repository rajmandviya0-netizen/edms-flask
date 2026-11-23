import { useEffect, useState } from "react";

const API_URL = "http://127.0.0.1:5000";

export default function App() {
  const [documents, setDocuments] = useState([]);
  const [file, setFile] = useState(null);
  const [department, setDepartment] = useState("General");
  const [referenceNumber, setReferenceNumber] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadDocuments() {
    setLoading(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch(`${API_URL}/api/documents`, {
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json" },
      });

      if (response.status === 401) {
        setError("Please sign in to Flask first.");
        setDocuments([]);
        return;
      }

      if (!response.ok) {
        throw new Error(`Could not load documents (${response.status}).`);
      }

      const data = await response.json();
      setDocuments(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || "Could not connect to Flask.");
      setDocuments([]);
    } finally {
      setLoading(false);
    }
  }

  async function uploadDocument(event) {
    event.preventDefault();
    setError("");
    setMessage("");

    if (!file) {
      setError("Please choose a file first.");
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setError("The file is larger than 10 MB.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("department", department);
    formData.append("reference_number", referenceNumber);
    formData.append("description", description);

    setUploading(true);

    try {
      const response = await fetch(`${API_URL}/api/documents/upload`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      const data = await response.json().catch(() => ({}));

      if (response.status === 401) {
        setError("Please sign in to Flask first, then try uploading again.");
        return;
      }

      if (!response.ok) {
        throw new Error(data.error || `Upload failed (${response.status}).`);
      }

      setMessage(data.message || "Document uploaded successfully.");
      setFile(null);
      event.target.reset();
      setDepartment("General");
      setReferenceNumber("");
      setDescription("");

      await loadDocuments();
    } catch (err) {
      setError(err.message || "Upload failed. Check that Flask is running.");
    } finally {
      setUploading(false);
    }
  }

  useEffect(() => {
    loadDocuments();
  }, []);

  return (
    <main style={styles.page}>
      <h1>Documents</h1>
      <p>Documents retrieved from the Flask API.</p>

      <p>
        <a href={`${API_URL}/login`} target="_blank" rel="noreferrer">
          Sign in to Flask
        </a>
      </p>

      <section style={styles.card}>
        <h2>Upload Document</h2>

        <form onSubmit={uploadDocument}>
          <label style={styles.label}>
            Select file
            <input
              type="file"
              accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.png,.jpg,.jpeg,.tif,.tiff"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </label>

          <label style={styles.label}>
            Department
            <input
              type="text"
              value={department}
              onChange={(event) => setDepartment(event.target.value)}
            />
          </label>

          <label style={styles.label}>
            Reference number
            <input
              type="text"
              value={referenceNumber}
              placeholder="Optional"
              onChange={(event) => setReferenceNumber(event.target.value)}
            />
          </label>

          <label style={styles.label}>
            Description
            <textarea
              value={description}
              placeholder="Optional"
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>

          <p>Maximum file size: 10 MB.</p>

          <button type="submit" disabled={uploading}>
            {uploading ? "Uploading..." : "Upload document"}
          </button>
        </form>
      </section>

      {error && <p role="alert" style={styles.error}>{error}</p>}
      {message && <p style={styles.success}>{message}</p>}

      <section style={styles.card}>
        <h2>Document List</h2>

        <button onClick={loadDocuments} disabled={loading}>
          {loading ? "Loading..." : "Refresh documents"}
        </button>

        {loading && <p>Loading documents...</p>}

        {!loading && !error && documents.length === 0 && (
          <p>No documents found.</p>
        )}

        <ul>
          {documents.map((doc) => (
            <li key={doc.id}>
              {doc.name || doc.filename || `Document ${doc.id}`}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}

const styles = {
  page: {
    maxWidth: "900px",
    margin: "0 auto",
    padding: "24px",
    fontFamily: "Arial, sans-serif",
  },
  card: {
    border: "1px solid #555",
    borderRadius: "8px",
    padding: "24px",
    margin: "24px 0",
  },
  label: {
    display: "block",
    margin: "16px 0",
  },
  error: {
    color: "crimson",
  },
  success: {
    color: "green",
  },
};