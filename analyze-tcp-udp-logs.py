import pandas as pd
import numpy as np
from datetime import datetime
import re
import json
from typing import Dict, List, Optional, Union
import logging
import os
import argparse
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Set up logging
logging.basicConfig(filename='traffic_analysis.log', level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s')

class TrafficAnalyzer:
    def __init__(self, log_file: str, config_file: Optional[str] = None):
        self.log_file = log_file
        self.df = None
        self.threats_detected = []
        
        # Default suspicious patterns
        self.suspicious_patterns = {
            'common_attack_ports': [22, 23, 80, 443, 3389, 445],
            'max_connections_per_ip': 100,
            'max_port_attempts': 50,
            'min_sources_for_suspicious_port': 10
        }
        
        # Load custom config if provided
        if config_file and os.path.exists(config_file):
            self.load_config(config_file)
            logging.info(f"Loaded custom configuration from {config_file}")
        
        # Track false positives
        self.false_positives = set()

    def load_config(self, config_file: str) -> None:
        """Load custom configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                custom_config = json.load(f)
                # Update only the keys that exist in the custom config
                for key, value in custom_config.items():
                    if key in self.suspicious_patterns:
                        self.suspicious_patterns[key] = value
                        logging.info(f"Updated {key} threshold to {value}")
        except Exception as e:
            logging.error(f"Error loading config file: {str(e)}")
            print(f"Warning: Could not load config file. Using default thresholds.")

    def load_logs(self) -> None:
        """Load and parse traffic logs into a DataFrame"""
        try:
            # Check if file exists
            if not os.path.exists(self.log_file):
                raise FileNotFoundError(f"Log file not found: {self.log_file}")
                
            # Detect file format based on first few lines
            with open(self.log_file, 'r') as f:
                first_line = f.readline().strip()
            
            # Determine delimiter based on file content
            if ',' in first_line:
                delimiter = ','
            elif '\t' in first_line:
                delimiter = '\t'
            else:
                delimiter = ' '
                
            # Assuming log format: timestamp,src_ip,dst_ip,protocol,src_port,dst_port,bytes
            expected_columns = ['timestamp', 'src_ip', 'dst_ip', 'protocol', 
                              'src_port', 'dst_port', 'bytes']
            
            # Try to read the CSV with detected delimiter
            self.df = pd.read_csv(self.log_file, delimiter=delimiter, 
                                names=expected_columns, 
                                parse_dates=['timestamp'])
            
            # Validate data
            missing_columns = [col for col in expected_columns if col not in self.df.columns]
            if missing_columns:
                logging.warning(f"Missing expected columns: {missing_columns}")
                
            # Convert port and bytes columns to numeric, handling errors
            for col in ['src_port', 'dst_port', 'bytes']:
                if col in self.df.columns:
                    self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
            
            self.df = self.df.dropna()  # Remove rows with NaN values
            logging.info(f"Successfully loaded {len(self.df)} log entries")
        except Exception as e:
            logging.error(f"Error loading logs: {str(e)}")
            raise

    def exclude_false_positive(self, ip_address: str) -> None:
        """Add an IP to the false positive list"""
        self.false_positives.add(ip_address)
        logging.info(f"Added {ip_address} to false positives list")
        
    def is_false_positive(self, ip_address: str) -> bool:
        """Check if an IP is in the false positive list"""
        return ip_address in self.false_positives

    def detect_port_scans(self) -> Dict:
        """Detect potential port scanning activities"""
        port_scan_attempts = {}
        
        # Group by source IP and count unique destination ports
        suspicious_ips = (self.df.groupby('src_ip')['dst_port']
                         .nunique()
                         .where(lambda x: x > self.suspicious_patterns['max_port_attempts'])
                         .dropna())
        
        for ip, port_count in suspicious_ips.items():
            # Skip false positives
            if self.is_false_positive(ip):
                continue
                
            timestamp = self.df[self.df['src_ip'] == ip]['timestamp'].max()
            port_scan_attempts[ip] = {
                'ports_scanned': int(port_count),
                'timestamp': timestamp.isoformat() if not pd.isna(timestamp) else None,
                'confidence': min(100, int(port_count / self.suspicious_patterns['max_port_attempts'] * 100))
            }
            self.threats_detected.append({
                'type': 'Port Scan',
                'src_ip': ip,
                'timestamp': timestamp.isoformat() if not pd.isna(timestamp) else None,
                'details': f"Scanned {port_count} unique ports",
                'confidence': port_scan_attempts[ip]['confidence']
            })
        
        return port_scan_attempts

    def detect_ddos(self) -> Dict:
        """Detect potential DDoS attempts based on connection volume"""
        ddos_attempts = {}
        
        # Group by source IP and count connections
        connection_counts = (self.df.groupby('src_ip')
                           .size()
                           .where(lambda x: x > self.suspicious_patterns['max_connections_per_ip'])
                           .dropna())
        
        for ip, count in connection_counts.items():
            # Skip false positives
            if self.is_false_positive(ip):
                continue
                
            avg_bytes = self.df[self.df['src_ip'] == ip]['bytes'].mean()
            ddos_attempts[ip] = {
                'connection_count': int(count),
                'avg_bytes': float(avg_bytes) if not pd.isna(avg_bytes) else 0,
                'confidence': min(100, int(count / self.suspicious_patterns['max_connections_per_ip'] * 100))
            }
            self.threats_detected.append({
                'type': 'Potential DDoS',
                'src_ip': ip,
                'details': f"{count} connections detected",
                'confidence': ddos_attempts[ip]['confidence']
            })
        
        return ddos_attempts

    def analyze_common_ports(self) -> Dict:
        """Analyze traffic to common attack ports"""
        port_traffic = {}
        
        suspicious_traffic = self.df[self.df['dst_port'].isin(
            self.suspicious_patterns['common_attack_ports'])]
        
        for port in self.suspicious_patterns['common_attack_ports']:
            port_data = suspicious_traffic[suspicious_traffic['dst_port'] == port]
            if not port_data.empty:
                unique_sources = port_data['src_ip'].nunique()
                port_traffic[port] = {
                    'connection_count': len(port_data),
                    'unique_sources': unique_sources,
                    'confidence': min(100, int(unique_sources / 
                                  self.suspicious_patterns['min_sources_for_suspicious_port'] * 100))
                }
                
                if unique_sources > self.suspicious_patterns['min_sources_for_suspicious_port']:
                    self.threats_detected.append({
                        'type': 'Suspicious Port Traffic',
                        'dst_port': port,
                        'details': f"{unique_sources} unique sources",
                        'confidence': port_traffic[port]['confidence']
                    })
        
        return port_traffic
    
    def detect_unusual_traffic_patterns(self) -> Dict:
        """Detect unusual traffic patterns based on statistical analysis"""
        unusual_patterns = {}
        
        # Calculate Z-scores for bytes transferred
        self.df['bytes_zscore'] = (self.df['bytes'] - self.df['bytes'].mean()) / self.df['bytes'].std()
        
        # Flag transfers with Z-score > 3 (outliers)
        unusual_transfers = self.df[self.df['bytes_zscore'] > 3]
        
        if not unusual_transfers.empty:
            # Group by source IP
            for ip, group in unusual_transfers.groupby('src_ip'):
                # Skip false positives
                if self.is_false_positive(ip):
                    continue
                    
                unusual_patterns[ip] = {
                    'count': len(group),
                    'max_bytes': group['bytes'].max(),
                    'avg_zscore': group['bytes_zscore'].mean()
                }
                
                self.threats_detected.append({
                    'type': 'Unusual Data Transfer',
                    'src_ip': ip,
                    'details': f"Transferred {group['bytes'].max()} bytes (Z-score: {group['bytes_zscore'].max():.2f})",
                    'confidence': min(100, int(group['bytes_zscore'].mean() * 20))  # Scale confidence
                })
        
        return unusual_patterns

    def visualize_threats(self, output_dir: str = '.') -> None:
        """Create visualizations of detected threats"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Ensure we have data to visualize
        if self.df is None or self.df.empty:
            logging.warning("No data available for visualization")
            return
            
        # Create a directory for the visualizations
        vis_dir = os.path.join(output_dir, 'visualizations')
        os.makedirs(vis_dir, exist_ok=True)
        
        # 1. Port scan visualization
        try:
            port_scans = self.detect_port_scans()
            if port_scans:
                plt.figure(figsize=(10, 6))
                ips = list(port_scans.keys())[:10]  # Limit to top 10
                ports = [port_scans[ip]['ports_scanned'] for ip in ips]
                
                plt.barh(ips, ports)
                plt.xlabel('Number of Ports Scanned')
                plt.ylabel('Source IP')
                plt.title('Top Port Scanning Activities')
                plt.tight_layout()
                plt.savefig(os.path.join(vis_dir, 'port_scans.png'))
                plt.close()
        except Exception as e:
            logging.error(f"Error creating port scan visualization: {str(e)}")
        
        # 2. Connection count visualization (DDoS)
        try:
            ddos_attempts = self.detect_ddos()
            if ddos_attempts:
                plt.figure(figsize=(10, 6))
                ips = list(ddos_attempts.keys())[:10]  # Limit to top 10
                counts = [ddos_attempts[ip]['connection_count'] for ip in ips]
                
                plt.barh(ips, counts)
                plt.xlabel('Number of Connections')
                plt.ylabel('Source IP')
                plt.title('Top Connection Counts (Potential DDoS)')
                plt.tight_layout()
                plt.savefig(os.path.join(vis_dir, 'ddos_attempts.png'))
                plt.close()
        except Exception as e:
            logging.error(f"Error creating DDoS visualization: {str(e)}")
        
        # 3. Traffic heatmap by hour and port
        try:
            # Extract hour from timestamp
            self.df['hour'] = self.df['timestamp'].dt.hour
            
            # Create a pivot table for the heatmap
            pivot = self.df.pivot_table(
                index='hour', 
                columns='dst_port', 
                values='bytes', 
                aggfunc='count',
                fill_value=0
            )
            
            # Limit to most common ports
            top_ports = self.df['dst_port'].value_counts().nlargest(10).index
            pivot = pivot[pivot.columns.intersection(top_ports)]
            
            plt.figure(figsize=(12, 8))
            sns.heatmap(pivot, cmap='YlOrRd', annot=False)
            plt.title('Traffic Heatmap by Hour and Destination Port')
            plt.tight_layout()
            plt.savefig(os.path.join(vis_dir, 'traffic_heatmap.png'))
            plt.close()
        except Exception as e:
            logging.error(f"Error creating traffic heatmap: {str(e)}")

    def generate_report(self, output_format: str = 'txt', output_dir: str = '.') -> str:
        """Generate a remediation report in the specified format"""
        if output_format not in ['txt', 'html', 'json']:
            logging.warning(f"Unsupported format: {output_format}. Using txt instead.")
            output_format = 'txt'
            
        # Create the output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        report_time = datetime.now().isoformat()
        
        # Generate visualizations
        self.visualize_threats(output_dir)
        
        # Collect threat data
        port_scans = self.detect_port_scans()
        ddos_attempts = self.detect_ddos()
        port_traffic = self.analyze_common_ports()
        unusual_patterns = self.detect_unusual_traffic_patterns()
        
        # Sort threats by confidence
        sorted_threats = sorted(self.threats_detected, 
                               key=lambda x: x.get('confidence', 0), 
                               reverse=True)
        
        if output_format == 'txt':
            # Text report
            report = f"Traffic Analysis Report - {report_time}\n"
            report += "=" * 50 + "\n\n"
            
            # Summary section
            report += "SUMMARY\n"
            report += "-------\n"
            report += f"Total log entries analyzed: {len(self.df)}\n"
            report += f"Distinct source IPs: {self.df['src_ip'].nunique()}\n"
            report += f"Distinct destination IPs: {self.df['dst_ip'].nunique()}\n"
            report += f"Date range: {self.df['timestamp'].min()} to {self.df['timestamp'].max()}\n"
            report += f"Total threats detected: {len(self.threats_detected)}\n\n"
            
            # Port scan analysis
            report += "Port Scan Detection:\n"
            if port_scans:
                for ip, details in port_scans.items():
                    report += f"IP: {ip} - Scanned {details['ports_scanned']} ports "
                    report += f"(Confidence: {details['confidence']}%)\n"
                    report += "Remediation: Block IP and investigate source\n\n"
            else:
                report += "No port scanning activity detected\n\n"
            
            # DDoS analysis
            report += "DDoS Detection:\n"
            if ddos_attempts:
                for ip, details in ddos_attempts.items():
                    report += f"IP: {ip} - {details['connection_count']} connections "
                    report += f"(Confidence: {details['confidence']}%)\n"
                    report += "Remediation: Rate limit or block IP, enable DDoS protection\n\n"
            else:
                report += "No DDoS activity detected\n\n"
            
            # Common ports analysis
            report += "Common Attack Port Traffic:\n"
            if port_traffic:
                for port, details in port_traffic.items():
                    report += f"Port {port}: {details['connection_count']} connections from "
                    report += f"{details['unique_sources']} sources "
                    if 'confidence' in details:
                        report += f"(Confidence: {details['confidence']}%)\n"
                    report += "Remediation: Monitor and consider port-specific filtering\n\n"
            else:
                report += "No suspicious port traffic detected\n\n"
            
            # Unusual traffic patterns
            report += "Unusual Traffic Patterns:\n"
            if unusual_patterns:
                for ip, details in unusual_patterns.items():
                    report += f"IP: {ip} - {details['count']} unusual transfers, "
                    report += f"max {details['max_bytes']} bytes\n"
                    report += "Remediation: Investigate for data exfiltration\n\n"
            else:
                report += "No unusual traffic patterns detected\n\n"
            
            # Save report
            report_path = os.path.join(output_dir, 'traffic_analysis_report.txt')
            with open(report_path, 'w') as f:
                f.write(report)
            
            return report
            
        elif output_format == 'html':
            # HTML report
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Traffic Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1, h2 {{ color: #2c3e50; }}
        .summary {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; }}
        .threat {{ margin-bottom: 20px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }}
        .high {{ background-color: #ffebee; }}
        .medium {{ background-color: #fff8e1; }}
        .low {{ background-color: #e8f5e9; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f2f2f2; }}
        .visualizations {{ display: flex; flex-wrap: wrap; justify-content: space-around; }}
        .vis-container {{ margin: 10px; max-width: 45%; }}
        img {{ max-width: 100%; height: auto; }}
    </style>
</head>
<body>
    <h1>Traffic Analysis Report</h1>
    <p>Generated on: {report_time}</p>
    
    <div class="summary">
        <h2>Summary</h2>
        <p>Total log entries analyzed: {len(self.df)}</p>
        <p>Distinct source IPs: {self.df['src_ip'].nunique()}</p>
        <p>Distinct destination IPs: {self.df['dst_ip'].nunique()}</p>
        <p>Date range: {self.df['timestamp'].min()} to {self.df['timestamp'].max()}</p>
        <p>Total threats detected: {len(self.threats_detected)}</p>
    </div>
    
    <h2>Detected Threats</h2>
    """
            
            # Add threat tables by type
            if sorted_threats:
                # Create a table of threats
                html += """
    <table>
        <tr>
            <th>Type</th>
            <th>Source/Target</th>
            <th>Details</th>
            <th>Confidence</th>
            <th>Recommended Action</th>
        </tr>
    """
                
                for threat in sorted_threats:
                    confidence = threat.get('confidence', 0)
                    confidence_class = 'high' if confidence > 80 else 'medium' if confidence > 50 else 'low'
                    
                    # Determine IP or port to display
                    target = threat.get('src_ip', threat.get('dst_port', 'N/A'))
                    
                    # Determine recommended action based on threat type
                    if threat['type'] == 'Port Scan':
                        action = "Block IP and investigate source"
                    elif threat['type'] == 'Potential DDoS':
                        action = "Rate limit or block IP, enable DDoS protection"
                    elif threat['type'] == 'Suspicious Port Traffic':
                        action = "Monitor and consider port-specific filtering"
                    elif threat['type'] == 'Unusual Data Transfer':
                        action = "Investigate for data exfiltration"
                    else:
                        action = "Investigate"
                    
                    html += f"""
        <tr class="{confidence_class}">
            <td>{threat['type']}</td>
            <td>{target}</td>
            <td>{threat['details']}</td>
            <td>{confidence}%</td>
            <td>{action}</td>
        </tr>
    """
                
                html += "</table>"
            else:
                html += "<p>No threats detected</p>"
            
            # Add visualizations section
            html += """
    <h2>Visualizations</h2>
    <div class="visualizations">
    """
            
            # Add visualization images if they exist
            vis_dir = os.path.join(output_dir, 'visualizations')
            if os.path.exists(vis_dir):
                for img_file in ['port_scans.png', 'ddos_attempts.png', 'traffic_heatmap.png']:
                    img_path = os.path.join(vis_dir, img_file)
                    if os.path.exists(img_path):
                        img_title = ' '.join(img_file.replace('.png', '').split('_')).title()
                        html += f"""
        <div class="vis-container">
            <h3>{img_title}</h3>
            <img src="visualizations/{img_file}" alt="{img_title}">
        </div>
        """
            
            html += """
    </div>
</body>
</html>
"""
            
            # Save HTML report
            report_path = os.path.join(output_dir, 'traffic_analysis_report.html')
            with open(report_path, 'w') as f:
                f.write(html)
            
            return report_path
            
        elif output_format == 'json':
            # JSON report
            json_report = {
                'timestamp': report_time,
                'summary': {
                    'total_entries': len(self.df),
                    'distinct_src_ips': self.df['src_ip'].nunique(),
                    'distinct_dst_ips': self.df['dst_ip'].nunique(),
                    'date_range': {
                        'start': self.df['timestamp'].min().isoformat(),
                        'end': self.df['timestamp'].max().isoformat()
                    },
                    'total_threats': len(self.threats_detected)
                },
                'threats': sorted_threats,
                'port_scans': port_scans,
                'ddos_attempts': ddos_attempts,
                'port_traffic': port_traffic,
                'unusual_patterns': unusual_patterns
            }
            
            # Save JSON report
            report_path = os.path.join(output_dir, 'traffic_analysis_report.json')
            with open(report_path, 'w') as f:
                json.dump(json_report, f, indent=2)
            
            return report_path


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Network Traffic Log Analyzer')
    parser.add_argument('--logfile', '-l', type=str, help='Path to the log file', required=False)
    parser.add_argument('--config', '-c', type=str, help='Path to custom configuration file', required=False)
    parser.add_argument('--output', '-o', type=str, default='txt', 
                       choices=['txt', 'html', 'json'], help='Output format (default: txt)')
    parser.add_argument('--outdir', '-d', type=str, default='.', 
                       help='Directory to save the report (default: current directory)')
    return parser.parse_args()


def main():
    """Main function to run the traffic analyzer"""
    args = parse_arguments()
    
    # If no log file is provided via command line, ask for it
    log_file = args.logfile
    if not log_file:
        log_file = input("Please enter the path to the traffic log file: ")
        print("NOTE: Make sure the log file is in the same folder as this script,", 
              "or provide the full path to the file.")
    
    # Verify the log file exists
    if not os.path.exists(log_file):
        print(f"Error: Log file '{log_file}' not found.")
        print("Please make sure the file exists and is in the correct location.")
        return
    
    # Initialize analyzer with log file and optional config
    analyzer = TrafficAnalyzer(log_file, args.config)
    
    try:
        # Load and analyze logs
        analyzer.load_logs()
        
        # Generate and display report
        report_path = analyzer.generate_report(args.output, args.outdir)
        
        print(f"\nAnalysis completed successfully.")
        print(f"Report saved to: {os.path.abspath(report_path)}")
        
        # If using HTML format, offer to open the report
        if args.output == 'html' and os.path.exists(report_path):
            import webbrowser
            open_report = input("Would you like to open the HTML report? (y/n): ")
            if open_report.lower() == 'y':
                webbrowser.open('file://' + os.path.abspath(report_path))
        
        # Save threats to JSON for further processing
        threats_path = os.path.join(args.outdir, 'threats_detected.json')
        with open(threats_path, 'w') as f:
            json.dump(analyzer.threats_detected, f, indent=2)
            
        logging.info("Analysis completed successfully")
        
    except Exception as e:
        logging.error(f"Analysis failed: {str(e)}")
        print(f"Error: {str(e)}")
        print("Check the log file 'traffic_analysis.log' for more details.")


if __name__ == "__main__":
    main()
