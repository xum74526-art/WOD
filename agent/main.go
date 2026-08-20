package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"syscall"
	"time"
)

var version = "dev"

const (
	heartbeatEvery = 30 * time.Second
	pollEvery      = 5 * time.Second
)

type config struct {
	APIURL     string `json:"api_url"`
	AgentID    string `json:"agent_id"`
	ServerNo   string `json:"server_no"`
	PrivateKey string `json:"private_key"`
}

type envelope struct {
	Data  json.RawMessage `json:"data"`
	Meta  json.RawMessage `json:"meta"`
	Error *struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

type enrollResponse struct {
	AgentID  string `json:"agent_id"`
	ServerNo string `json:"server_no"`
}

type command struct {
	CommandNo      string         `json:"command_no"`
	Action         string         `json:"action"`
	Payload        map[string]any `json:"payload"`
	LeaseNo        string         `json:"lease_no"`
	DurationHours  int            `json:"duration_hours"`
	ExpiresAt      *time.Time     `json:"expires_at"`
	GraceExpiresAt *time.Time     `json:"grace_expires_at"`
}

type leaseState struct {
	LeaseNo        string    `json:"lease_no"`
	Username       string    `json:"username"`
	PublicKey      string    `json:"public_key,omitempty"`
	Status         string    `json:"status"`
	ExpiresAt      time.Time `json:"expires_at"`
	GraceExpiresAt time.Time `json:"grace_expires_at"`
}

type stateFile struct {
	Leases map[string]leaseState `json:"leases"`
}

type agent struct {
	cfg        config
	configPath string
	statePath  string
	client     *http.Client
	privateKey ed25519.PrivateKey
	mu         sync.Mutex
	state      stateFile
}

func main() {
	log.SetFlags(log.LstdFlags | log.LUTC)
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	var err error
	switch os.Args[1] {
	case "inventory":
		err = inventoryCommand()
	case "check":
		err = serviceCheckCommand()
	case "enroll":
		err = enroll(os.Args[2:])
	case "run":
		err = run(os.Args[2:], false)
	case "once":
		err = run(os.Args[2:], true)
	case "version", "--version", "-version":
		fmt.Printf("kai-agent %s %s/%s\n", version, runtime.GOOS, runtime.GOARCH)
		return
	default:
		usage()
		err = fmt.Errorf("unknown command %q", os.Args[1])
	}
	if err != nil {
		log.Printf("ERROR: %v", err)
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "KAI Agent - restricted SSH lease agent")
	fmt.Fprintln(os.Stderr, "usage: kai-agent inventory")
	fmt.Fprintln(os.Stderr, "usage: kai-agent check")
	fmt.Fprintln(os.Stderr, "usage: kai-agent enroll --api-url URL --token TOKEN [--config PATH]")
	fmt.Fprintln(os.Stderr, "       kai-agent run [--config PATH]")
	fmt.Fprintln(os.Stderr, "       kai-agent once [--config PATH]")
	fmt.Fprintln(os.Stderr, "       kai-agent version")
}

func defaultConfigPath() string {
	if runtime.GOOS == "windows" {
		base := os.Getenv("ProgramData")
		if base == "" {
			base = `C:\ProgramData`
		}
		return filepath.Join(base, "KAI", "Agent", "config.json")
	}
	return "/etc/kai-agent/config.json"
}

func defaultStatePath() string {
	if runtime.GOOS == "windows" {
		base := os.Getenv("ProgramData")
		if base == "" {
			base = `C:\ProgramData`
		}
		return filepath.Join(base, "KAI", "Agent", "leases.json")
	}
	return "/var/lib/kai-agent/leases.json"
}

func capabilities() []string {
	return []string{"authorize_key", "revoke_key", "cleanup_account", "offline_expiry"}
}

func enroll(args []string) error {
	flags := flag.NewFlagSet("enroll", flag.ContinueOnError)
	apiURL := flags.String("api-url", os.Getenv("KAI_API_URL"), "platform API base URL")
	token := flags.String("token", os.Getenv("KAI_ENROLLMENT_TOKEN"), "single-use enrollment token")
	configPath := flags.String("config", defaultConfigPath(), "config file path")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if strings.TrimSpace(*apiURL) == "" || strings.TrimSpace(*token) == "" {
		return errors.New("--api-url and --token are required")
	}
	parsed, err := url.Parse(strings.TrimRight(*apiURL, "/"))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return errors.New("--api-url must be an absolute http(s) URL")
	}
	if parsed.Scheme != "https" && parsed.Hostname() != "127.0.0.1" && parsed.Hostname() != "localhost" && parsed.Hostname() != "host.docker.internal" {
		return errors.New("HTTPS is required unless the platform runs on localhost")
	}
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return fmt.Errorf("generate device identity: %w", err)
	}
	hostname, _ := os.Hostname()
	payload := map[string]any{
		"enrollment_token":  *token,
		"device_public_key": base64.StdEncoding.EncodeToString(publicKey),
		"platform":          runtime.GOOS,
		"arch":              runtime.GOARCH,
		"hostname":          hostname,
		"version":           version,
		"capabilities":      capabilities(),
		"inventory":         collectInventory(),
		"service_checks":    collectServiceChecks(),
	}
	body, _ := json.Marshal(payload)
	response, err := http.Post(strings.TrimRight(*apiURL, "/")+"/api/v1/agent/enroll", "application/json", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("enroll request: %w", err)
	}
	defer response.Body.Close()
	data, err := parseEnvelope(response)
	if err != nil {
		return err
	}
	var enrolled enrollResponse
	if err := json.Unmarshal(data, &enrolled); err != nil {
		return err
	}
	cfg := config{
		APIURL:     strings.TrimRight(*apiURL, "/"),
		AgentID:    enrolled.AgentID,
		ServerNo:   enrolled.ServerNo,
		PrivateKey: base64.StdEncoding.EncodeToString(privateKey),
	}
	if err := writeJSONAtomic(*configPath, cfg, 0600); err != nil {
		return fmt.Errorf("write config: %w", err)
	}
	fmt.Printf("Agent enrolled: %s (%s)\n", enrolled.ServerNo, enrolled.AgentID)
	return nil
}

func run(args []string, once bool) error {
	flags := flag.NewFlagSet("run", flag.ContinueOnError)
	configPath := flags.String("config", defaultConfigPath(), "config file path")
	statePath := flags.String("state", defaultStatePath(), "offline lease state file")
	if err := flags.Parse(args); err != nil {
		return err
	}
	a, err := newAgent(*configPath, *statePath)
	if err != nil {
		return err
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	if once {
		return a.cycle(ctx)
	}
	log.Printf("KAI Agent %s started for %s", version, a.cfg.ServerNo)
	heartbeatTicker := time.NewTicker(heartbeatEvery)
	pollTicker := time.NewTicker(pollEvery)
	offlineTicker := time.NewTicker(time.Second)
	defer heartbeatTicker.Stop()
	defer pollTicker.Stop()
	defer offlineTicker.Stop()
	if err := a.heartbeat(ctx); err != nil {
		log.Printf("heartbeat: %v", err)
	}
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-heartbeatTicker.C:
			if err := a.heartbeat(ctx); err != nil {
				log.Printf("heartbeat: %v", err)
			}
		case <-pollTicker.C:
			if err := a.poll(ctx); err != nil {
				log.Printf("poll: %v", err)
			}
		case <-offlineTicker.C:
			if err := a.enforceOfflineDeadlines(); err != nil {
				log.Printf("offline expiry: %v", err)
			}
		}
	}
}

func newAgent(configPath, statePath string) (*agent, error) {
	var cfg config
	if err := readJSON(configPath, &cfg); err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}
	privateKey, err := base64.StdEncoding.DecodeString(cfg.PrivateKey)
	if err != nil || len(privateKey) != ed25519.PrivateKeySize {
		return nil, errors.New("invalid device private key")
	}
	a := &agent{
		cfg: cfg, configPath: configPath, statePath: statePath,
		client: &http.Client{Timeout: 35 * time.Second}, privateKey: ed25519.PrivateKey(privateKey),
		state: stateFile{Leases: map[string]leaseState{}},
	}
	if err := readJSON(statePath, &a.state); err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	if a.state.Leases == nil {
		a.state.Leases = map[string]leaseState{}
	}
	return a, nil
}

func (a *agent) cycle(ctx context.Context) error {
	if err := a.heartbeat(ctx); err != nil {
		return err
	}
	if err := a.enforceOfflineDeadlines(); err != nil {
		return err
	}
	return a.poll(ctx)
}

func (a *agent) heartbeat(ctx context.Context) error {
	hostname, _ := os.Hostname()
	payload := map[string]any{
		"version": version, "hostname": hostname, "platform": runtime.GOOS,
		"arch": runtime.GOARCH, "capabilities": capabilities(), "inventory": collectInventory(),
		"service_checks": collectServiceChecks(),
	}
	_, err := a.request(ctx, http.MethodPost, "/api/v1/agent/heartbeat", payload)
	return err
}

func (a *agent) poll(ctx context.Context) error {
	data, err := a.request(ctx, http.MethodGet, "/api/v1/agent/commands/next", nil)
	if err != nil {
		return err
	}
	if bytes.Equal(bytes.TrimSpace(data), []byte("null")) {
		return nil
	}
	var cmd command
	if err := json.Unmarshal(data, &cmd); err != nil {
		return err
	}
	message, executeErr := a.execute(cmd)
	result := map[string]any{"success": executeErr == nil, "message": message}
	if executeErr != nil {
		result["message"] = executeErr.Error()
	}
	_, reportErr := a.request(ctx, http.MethodPost,
		"/api/v1/agent/commands/"+url.PathEscape(cmd.CommandNo)+"/result", result)
	if reportErr != nil {
		return fmt.Errorf("report command %s: %w", cmd.CommandNo, reportErr)
	}
	if executeErr != nil {
		return executeErr
	}
	log.Printf("command %s %s succeeded", cmd.CommandNo, cmd.Action)
	return nil
}

func (a *agent) execute(cmd command) (string, error) {
	username, _ := cmd.Payload["username"].(string)
	switch cmd.Action {
	case "authorize_key":
		publicKey, _ := cmd.Payload["public_key"].(string)
		if err := authorizeKey(username, publicKey); err != nil {
			return "", err
		}
		now := time.Now().UTC()
		expires := cmd.ExpiresAt
		if raw, ok := cmd.Payload["expires_at"].(string); ok && raw != "" {
			if parsed, err := time.Parse(time.RFC3339, raw); err == nil {
				expires = &parsed
			}
		}
		if expires == nil {
			hours := cmd.DurationHours
			if value, ok := cmd.Payload["duration_hours"].(float64); ok {
				hours = int(value)
			}
			if hours < 1 {
				hours = 1
			}
			value := now.Add(time.Duration(hours) * time.Hour)
			expires = &value
		}
		grace := cmd.GraceExpiresAt
		if raw, ok := cmd.Payload["grace_expires_at"].(string); ok && raw != "" {
			if parsed, err := time.Parse(time.RFC3339, raw); err == nil {
				grace = &parsed
			}
		}
		if grace == nil {
			value := expires.Add(2 * time.Hour)
			grace = &value
		}
		a.setLease(leaseState{LeaseNo: cmd.LeaseNo, Username: username, PublicKey: publicKey, Status: "active", ExpiresAt: *expires, GraceExpiresAt: *grace})
		return "SSH public key authorized", nil
	case "revoke_key":
		if err := revokeKey(username); err != nil {
			return "", err
		}
		a.updateLease(cmd.LeaseNo, func(item *leaseState) { item.Status = "grace" })
		return "SSH access revoked", nil
	case "cleanup_account":
		if err := cleanupAccount(username); err != nil {
			return "", err
		}
		a.deleteLease(cmd.LeaseNo)
		return "lease account and data removed", nil
	default:
		return "", fmt.Errorf("unsupported restricted action %q", cmd.Action)
	}
}

func (a *agent) enforceOfflineDeadlines() error {
	a.mu.Lock()
	defer a.mu.Unlock()
	now := time.Now().UTC()
	changed := false
	for leaseNo, item := range a.state.Leases {
		if item.Status == "active" && !item.ExpiresAt.IsZero() && !now.Before(item.ExpiresAt) {
			if err := revokeKey(item.Username); err != nil {
				return err
			}
			item.Status = "grace"
			a.state.Leases[leaseNo] = item
			changed = true
			log.Printf("offline safeguard revoked lease %s", leaseNo)
		}
		if item.Status == "grace" && !item.GraceExpiresAt.IsZero() && !now.Before(item.GraceExpiresAt) {
			if err := cleanupAccount(item.Username); err != nil {
				return err
			}
			delete(a.state.Leases, leaseNo)
			changed = true
			log.Printf("offline safeguard cleaned lease %s", leaseNo)
		}
	}
	if changed {
		return writeJSONAtomic(a.statePath, a.state, 0600)
	}
	return nil
}

func (a *agent) setLease(item leaseState) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.state.Leases[item.LeaseNo] = item
	if err := writeJSONAtomic(a.statePath, a.state, 0600); err != nil {
		log.Printf("save lease state: %v", err)
	}
}
func (a *agent) updateLease(no string, fn func(*leaseState)) {
	a.mu.Lock()
	defer a.mu.Unlock()
	item, ok := a.state.Leases[no]
	if !ok {
		return
	}
	fn(&item)
	a.state.Leases[no] = item
	if err := writeJSONAtomic(a.statePath, a.state, 0600); err != nil {
		log.Printf("save lease state: %v", err)
	}
}
func (a *agent) deleteLease(no string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	delete(a.state.Leases, no)
	if err := writeJSONAtomic(a.statePath, a.state, 0600); err != nil {
		log.Printf("save lease state: %v", err)
	}
}

func (a *agent) request(ctx context.Context, method, path string, payload any) (json.RawMessage, error) {
	var body []byte
	if payload != nil {
		body, _ = json.Marshal(payload)
	}
	req, err := http.NewRequestWithContext(ctx, method, a.cfg.APIURL+path, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	timestamp := fmt.Sprintf("%d", time.Now().Unix())
	nonceBytes := make([]byte, 16)
	if _, err := rand.Read(nonceBytes); err != nil {
		return nil, err
	}
	nonce := hex.EncodeToString(nonceBytes)
	hash := sha256.Sum256(body)
	canonical := strings.Join([]string{method, req.URL.Path, timestamp, nonce, hex.EncodeToString(hash[:])}, "\n")
	signature := ed25519.Sign(a.privateKey, []byte(canonical))
	req.Header.Set("X-KAI-Agent-ID", a.cfg.AgentID)
	req.Header.Set("X-KAI-Timestamp", timestamp)
	req.Header.Set("X-KAI-Nonce", nonce)
	req.Header.Set("X-KAI-Signature", base64.StdEncoding.EncodeToString(signature))
	response, err := a.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	return parseEnvelope(response)
}

func parseEnvelope(response *http.Response) (json.RawMessage, error) {
	body, err := io.ReadAll(io.LimitReader(response.Body, 2<<20))
	if err != nil {
		return nil, err
	}
	var value envelope
	if err := json.Unmarshal(body, &value); err != nil {
		return nil, fmt.Errorf("platform returned %s: %s", response.Status, strings.TrimSpace(string(body)))
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		if value.Error != nil {
			return nil, fmt.Errorf("%s: %s", value.Error.Code, value.Error.Message)
		}
		return nil, fmt.Errorf("platform returned %s", response.Status)
	}
	return value.Data, nil
}

func readJSON(path string, target any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, target)
}

func writeJSONAtomic(path string, value any, mode os.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	temp := path + ".tmp"
	if err := os.WriteFile(temp, append(data, '\n'), mode); err != nil {
		return err
	}
	return os.Rename(temp, path)
}
