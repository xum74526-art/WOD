package main

import (
	"encoding/json"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
	"time"
)

type sshServiceCheck struct {
	Reachable bool   `json:"reachable"`
	Port      int    `json:"port"`
	Error     string `json:"error,omitempty"`
}

type serviceChecks struct {
	CheckedAt time.Time       `json:"checked_at"`
	SSH       sshServiceCheck `json:"ssh"`
}

func localSSHPort() int {
	value := strings.TrimSpace(os.Getenv("KAI_AGENT_SSH_LOCAL_PORT"))
	if value == "" {
		return 22
	}
	port, err := strconv.Atoi(value)
	if err != nil || port < 1 || port > 65535 {
		return 22
	}
	return port
}

func collectServiceChecks() serviceChecks {
	port := localSSHPort()
	check := serviceChecks{
		CheckedAt: time.Now().UTC(),
		SSH:       sshServiceCheck{Port: port},
	}
	connection, err := net.DialTimeout("tcp", net.JoinHostPort("127.0.0.1", strconv.Itoa(port)), 2*time.Second)
	if err != nil {
		check.SSH.Error = err.Error()
		return check
	}
	check.SSH.Reachable = true
	_ = connection.Close()
	return check
}

func serviceCheckCommand() error {
	checks := collectServiceChecks()
	data, err := json.MarshalIndent(checks, "", "  ")
	if err != nil {
		return err
	}
	fmt.Println(string(data))
	if !checks.SSH.Reachable {
		return fmt.Errorf("SSH service is not reachable on local port %d", checks.SSH.Port)
	}
	return nil
}
