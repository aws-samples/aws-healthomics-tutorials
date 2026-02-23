// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.tsv

case class TSVOptions(
    annotationType: Option[String],
    formatToHeader: Option[Map[String, String]],
    schema: Option[String],
    readOptions: Option[Map[String, String]])
