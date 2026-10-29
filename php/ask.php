<?php
header("Content-Type: application/json; charset=utf-8");

$q = trim($_POST["q"] ?? "");
if (!$q) {
    echo json_encode(["error" => "empty question"]);
    exit;
}

$ch = curl_init("http://127.0.0.1:9001/ask");
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_POST => true,
    CURLOPT_HTTPHEADER => ["Content-Type: application/json"],
    CURLOPT_POSTFIELDS => json_encode(["q" => $q]),
]);

$res = curl_exec($ch);
echo $res;
