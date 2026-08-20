//go:build linux

package main

import (
	"fmt"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

var linuxUsername = regexp.MustCompile(`^[a-z_][a-z0-9_-]{0,31}$`)

func validateUsername(name string) error {
	if !linuxUsername.MatchString(name) || name == "root" {
		return fmt.Errorf("unsafe lease username")
	}
	return nil
}

func lookupOrCreateUser(name string) (*user.User, error) {
	if err := validateUsername(name); err != nil {
		return nil, err
	}
	entry, err := user.Lookup(name)
	if err == nil {
		return entry, nil
	}
	if _, ok := err.(user.UnknownUserError); !ok {
		return nil, err
	}
	if output, createErr := exec.Command("useradd", "--create-home", "--shell", "/bin/bash", name).CombinedOutput(); createErr != nil {
		return nil, fmt.Errorf("create lease user: %s", strings.TrimSpace(string(output)))
	}
	return user.Lookup(name)
}

func authorizeKey(name, publicKey string) error {
	if !strings.HasPrefix(publicKey, "ssh-") && !strings.HasPrefix(publicKey, "ecdsa-") {
		return fmt.Errorf("invalid SSH public key")
	}
	entry, err := lookupOrCreateUser(name)
	if err != nil {
		return err
	}
	uid, err := strconv.Atoi(entry.Uid)
	if err != nil {
		return err
	}
	gid, err := strconv.Atoi(entry.Gid)
	if err != nil {
		return err
	}
	sshDir := filepath.Join(entry.HomeDir, ".ssh")
	if err := os.MkdirAll(sshDir, 0700); err != nil {
		return err
	}
	if err := os.Chown(sshDir, uid, gid); err != nil {
		return err
	}
	keyPath := filepath.Join(sshDir, "authorized_keys")
	if err := os.WriteFile(keyPath, []byte(strings.TrimSpace(publicKey)+"\n"), 0600); err != nil {
		return err
	}
	return os.Chown(keyPath, uid, gid)
}

func revokeKey(name string) error {
	if err := validateUsername(name); err != nil {
		return err
	}
	if entry, err := user.Lookup(name); err == nil {
		_ = os.Remove(filepath.Join(entry.HomeDir, ".ssh", "authorized_keys"))
		_ = exec.Command("pkill", "-KILL", "-u", name).Run()
	} else if _, ok := err.(user.UnknownUserError); !ok {
		return err
	}
	return nil
}

func cleanupAccount(name string) error {
	if err := validateUsername(name); err != nil {
		return err
	}
	if _, err := user.Lookup(name); err != nil {
		if _, ok := err.(user.UnknownUserError); ok {
			return nil
		}
		return err
	}
	output, err := exec.Command("userdel", "--remove", name).CombinedOutput()
	if err != nil {
		return fmt.Errorf("remove lease user: %s", strings.TrimSpace(string(output)))
	}
	return nil
}
