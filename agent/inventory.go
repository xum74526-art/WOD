package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

type gpuInventory struct {
	Index         int    `json:"index"`
	Name          string `json:"name"`
	MemoryTotalMB int    `json:"memory_total_mb"`
	UUID          string `json:"uuid,omitempty"`
	DriverVersion string `json:"driver_version,omitempty"`
}

type hardwareInventory struct {
	CollectedAt      time.Time      `json:"collected_at"`
	Source           string         `json:"source"`
	OSName           string         `json:"os_name"`
	OSVersion        string         `json:"os_version,omitempty"`
	KernelVersion    string         `json:"kernel_version,omitempty"`
	CPUModel         string         `json:"cpu_model"`
	CPULogicalCores  int            `json:"cpu_logical_cores"`
	MemoryTotalMB    int64          `json:"memory_total_mb"`
	DiskTotalGB      int64          `json:"disk_total_gb"`
	DiskAvailableGB  int64          `json:"disk_available_gb"`
	GPUs             []gpuInventory `json:"gpus"`
	CollectionErrors []string       `json:"collection_errors"`
}

func inventoryCommand() error {
	value := collectInventory()
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	fmt.Println(string(data))
	return nil
}

func collectInventory() hardwareInventory {
	value := hardwareInventory{
		CollectedAt:      time.Now().UTC(),
		Source:           inventorySource(),
		OSName:           runtime.GOOS,
		CPULogicalCores:  runtime.NumCPU(),
		GPUs:             []gpuInventory{},
		CollectionErrors: []string{},
	}
	if runtime.GOOS == "windows" {
		collectWindowsInventory(&value)
	} else {
		collectLinuxInventory(&value)
	}
	value.GPUs = collectNvidiaGPUs(&value)
	if value.CPUModel == "" {
		value.CPUModel = "unknown"
	}
	return value
}

func inventorySource() string {
	if strings.EqualFold(strings.TrimSpace(os.Getenv("KAI_AGENT_RUNTIME")), "docker") {
		return "docker"
	}
	if _, err := os.Stat("/.dockerenv"); err == nil {
		return "docker"
	}
	return "host"
}

func addInventoryError(value *hardwareInventory, code string) {
	for _, item := range value.CollectionErrors {
		if item == code {
			return
		}
	}
	value.CollectionErrors = append(value.CollectionErrors, code)
}

func collectLinuxInventory(value *hardwareInventory) {
	if data, err := os.ReadFile("/etc/os-release"); err == nil {
		fields := parseKeyValueFile(data)
		if name := fields["PRETTY_NAME"]; name != "" {
			value.OSName = name
		}
		value.OSVersion = fields["VERSION_ID"]
	}
	if output, err := runCommand("uname", "-r"); err == nil {
		value.KernelVersion = strings.TrimSpace(output)
	}
	if data, err := os.ReadFile("/proc/cpuinfo"); err == nil {
		scanner := bufio.NewScanner(bytes.NewReader(data))
		for scanner.Scan() {
			line := scanner.Text()
			parts := strings.SplitN(line, ":", 2)
			if len(parts) == 2 && (strings.TrimSpace(parts[0]) == "model name" || strings.TrimSpace(parts[0]) == "Hardware") {
				value.CPUModel = strings.TrimSpace(parts[1])
				break
			}
		}
	} else {
		addInventoryError(value, "cpu_info_unavailable")
	}
	if data, err := os.ReadFile("/proc/meminfo"); err == nil {
		scanner := bufio.NewScanner(bytes.NewReader(data))
		for scanner.Scan() {
			fields := strings.Fields(scanner.Text())
			if len(fields) >= 2 && fields[0] == "MemTotal:" {
				kb, _ := strconv.ParseInt(fields[1], 10, 64)
				value.MemoryTotalMB = kb / 1024
				break
			}
		}
	} else {
		addInventoryError(value, "memory_info_unavailable")
	}
	if output, err := runCommand("df", "-Pk", "/"); err == nil {
		lines := strings.Split(strings.TrimSpace(output), "\n")
		if len(lines) >= 2 {
			fields := strings.Fields(lines[len(lines)-1])
			if len(fields) >= 4 {
				totalKB, _ := strconv.ParseInt(fields[1], 10, 64)
				availableKB, _ := strconv.ParseInt(fields[3], 10, 64)
				value.DiskTotalGB = totalKB / 1024 / 1024
				value.DiskAvailableGB = availableKB / 1024 / 1024
			}
		}
	} else {
		addInventoryError(value, "disk_info_unavailable")
	}
}

func collectWindowsInventory(value *hardwareInventory) {
	const script = `$ErrorActionPreference='Stop'; $os=Get-CimInstance Win32_OperatingSystem; $cpu=Get-CimInstance Win32_Processor | Select-Object -First 1; $disk=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$env:SystemDrive'"; [ordered]@{os_name=$os.Caption;os_version=$os.Version;kernel_version=$os.BuildNumber;cpu_model=$cpu.Name;memory_total_mb=[math]::Floor($os.TotalVisibleMemorySize/1024);disk_total_gb=[math]::Floor($disk.Size/1GB);disk_available_gb=[math]::Floor($disk.FreeSpace/1GB)} | ConvertTo-Json -Compress`
	output, err := runCommand("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script)
	if err != nil {
		addInventoryError(value, "windows_inventory_unavailable")
		return
	}
	var parsed struct {
		OSName          string `json:"os_name"`
		OSVersion       string `json:"os_version"`
		KernelVersion   string `json:"kernel_version"`
		CPUModel        string `json:"cpu_model"`
		MemoryTotalMB   int64  `json:"memory_total_mb"`
		DiskTotalGB     int64  `json:"disk_total_gb"`
		DiskAvailableGB int64  `json:"disk_available_gb"`
	}
	if err := json.Unmarshal([]byte(strings.TrimSpace(output)), &parsed); err != nil {
		addInventoryError(value, "windows_inventory_invalid")
		return
	}
	value.OSName = parsed.OSName
	value.OSVersion = parsed.OSVersion
	value.KernelVersion = parsed.KernelVersion
	value.CPUModel = parsed.CPUModel
	value.MemoryTotalMB = parsed.MemoryTotalMB
	value.DiskTotalGB = parsed.DiskTotalGB
	value.DiskAvailableGB = parsed.DiskAvailableGB
}

func collectNvidiaGPUs(value *hardwareInventory) []gpuInventory {
	binary := "nvidia-smi"
	if runtime.GOOS == "windows" {
		if _, err := exec.LookPath(binary); err != nil {
			candidate := filepath.Join(os.Getenv("ProgramFiles"), "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe")
			if _, statErr := os.Stat(candidate); statErr == nil {
				binary = candidate
			}
		}
	}
	if _, err := exec.LookPath(binary); err != nil && !filepath.IsAbs(binary) {
		addInventoryError(value, "nvidia_smi_not_found")
		return []gpuInventory{}
	}
	output, err := runCommand(binary, "--query-gpu=index,name,memory.total,uuid,driver_version", "--format=csv,noheader,nounits")
	if err != nil {
		addInventoryError(value, "nvidia_smi_failed")
		return []gpuInventory{}
	}
	items := []gpuInventory{}
	for _, line := range strings.Split(strings.TrimSpace(output), "\n") {
		if strings.TrimSpace(line) == "" {
			continue
		}
		fields := strings.SplitN(line, ",", 5)
		if len(fields) != 5 {
			addInventoryError(value, "nvidia_smi_output_invalid")
			continue
		}
		index, indexErr := strconv.Atoi(strings.TrimSpace(fields[0]))
		memory, memoryErr := strconv.Atoi(strings.TrimSpace(fields[2]))
		if indexErr != nil || memoryErr != nil {
			addInventoryError(value, "nvidia_smi_output_invalid")
			continue
		}
		items = append(items, gpuInventory{
			Index:         index,
			Name:          strings.TrimSpace(fields[1]),
			MemoryTotalMB: memory,
			UUID:          strings.TrimSpace(fields[3]),
			DriverVersion: strings.TrimSpace(fields[4]),
		})
	}
	return items
}

func parseKeyValueFile(data []byte) map[string]string {
	result := map[string]string{}
	scanner := bufio.NewScanner(bytes.NewReader(data))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) == 2 {
			result[parts[0]] = strings.Trim(strings.TrimSpace(parts[1]), `"'`)
		}
	}
	return result
}

func runCommand(name string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, name, args...)
	var output bytes.Buffer
	cmd.Stdout = &output
	cmd.Stderr = nil
	if err := cmd.Run(); err != nil {
		return "", err
	}
	if err := ctx.Err(); err != nil {
		return "", err
	}
	return output.String(), nil
}
