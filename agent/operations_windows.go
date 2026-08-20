//go:build windows

package main

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
)

var windowsUsername = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_-]{0,19}$`)

func validateUsername(name string) error {
	if !windowsUsername.MatchString(name) || strings.EqualFold(name, "Administrator") {
		return fmt.Errorf("unsafe lease username")
	}
	return nil
}

func windowsUserExists(name string) bool { return exec.Command("net", "user", name).Run() == nil }

func authorizeKey(name, publicKey string) error {
	if err := validateUsername(name); err != nil {
		return err
	}
	if !strings.HasPrefix(publicKey, "ssh-") && !strings.HasPrefix(publicKey, "ecdsa-") {
		return fmt.Errorf("invalid SSH public key")
	}
	if !windowsUserExists(name) {
		secret := make([]byte, 24)
		if _, err := rand.Read(secret); err != nil {
			return err
		}
		password := "W0d!" + base64.RawURLEncoding.EncodeToString(secret)
		if output, err := exec.Command("net", "user", name, password, "/add", "/expires:never").CombinedOutput(); err != nil {
			return fmt.Errorf("create lease user: %s", strings.TrimSpace(string(output)))
		}
	}
	home := filepath.Join(os.Getenv("SystemDrive")+`\`, "Users", name)
	sshDir := filepath.Join(home, ".ssh")
	if err := os.MkdirAll(sshDir, 0700); err != nil {
		return err
	}
	keyPath := filepath.Join(sshDir, "authorized_keys")
	if err := os.WriteFile(keyPath, []byte(strings.TrimSpace(publicKey)+"\r\n"), 0600); err != nil {
		return err
	}
	_ = exec.Command("icacls", sshDir, "/inheritance:r", "/grant", name+":(OI)(CI)F", "/grant", "SYSTEM:(OI)(CI)F").Run()
	_ = exec.Command("icacls", keyPath, "/inheritance:r", "/grant", name+":F", "/grant", "SYSTEM:F").Run()
	return nil
}

func revokeKey(name string) error {
	if err := validateUsername(name); err != nil {
		return err
	}
	keyPath := filepath.Join(os.Getenv("SystemDrive")+`\`, "Users", name, ".ssh", "authorized_keys")
	if err := os.Remove(keyPath); err != nil && !os.IsNotExist(err) {
		return err
	}
	_ = exec.Command("taskkill", "/F", "/FI", "USERNAME eq "+name).Run()
	return nil
}

func cleanupAccount(name string) error {
	if err := validateUsername(name); err != nil {
		return err
	}
	if windowsUserExists(name) {
		if output, err := exec.Command("net", "user", name, "/delete").CombinedOutput(); err != nil {
			return fmt.Errorf("remove lease user: %s", strings.TrimSpace(string(output)))
		}
	}
	return os.RemoveAll(filepath.Join(os.Getenv("SystemDrive")+`\`, "Users", name))
}
