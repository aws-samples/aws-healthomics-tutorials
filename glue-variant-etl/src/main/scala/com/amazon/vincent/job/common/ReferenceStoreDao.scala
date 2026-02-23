// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.common

import com.amazon.vincent.job.models.ReferenceStoreItem
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider
import software.amazon.awssdk.awscore.{AwsRequest, AwsRequestOverrideConfiguration}
import software.amazon.awssdk.services.omics.OmicsClient
import software.amazon.awssdk.services.omics.model.{
  GetReferenceMetadataRequest,
  GetReferenceRequest
}

import java.io.FileOutputStream

case class ReferenceStoreDao(omicsClient: OmicsClient) {

  implicit class CredentialProviderOmicsRequest[T <: AwsRequest.Builder](awsRequestBuilder: T) {
    def credentialProvider(awsCredentialProvider: Option[AwsCredentialsProvider]): T = {
      awsCredentialProvider match {
        case Some(value) =>
          val overwrite = AwsRequestOverrideConfiguration
            .builder()
            .credentialsProvider(value)
            .build()
          awsRequestBuilder.overrideConfiguration(overwrite).asInstanceOf[T]
        case None => awsRequestBuilder
      }
    }
  }

  def getReferencePartsCount(
      referenceStoreItem: ReferenceStoreItem,
      credentialsProvider: Option[AwsCredentialsProvider] = None): Integer = {
    val request: GetReferenceMetadataRequest = GetReferenceMetadataRequest
      .builder()
      .referenceStoreId(referenceStoreItem.referenceStoreId)
      .id(referenceStoreItem.referenceId)
      .credentialProvider(credentialsProvider)
      .build()
    omicsClient.getReferenceMetadata(request).files().source().totalParts
  }

  def getReferenceAsByteArray(
      referenceStoreItem: ReferenceStoreItem,
      partNumber: Integer,
      credentialsProvider: Option[AwsCredentialsProvider] = None): Array[Byte] = {
    val referenceRequest = GetReferenceRequest
      .builder()
      .referenceStoreId(referenceStoreItem.referenceStoreId)
      .id(referenceStoreItem.referenceId)
      .partNumber(partNumber)
      .credentialProvider(credentialsProvider)
      .build()
    val fastaBytes = omicsClient.getReferenceAsBytes(referenceRequest)
    fastaBytes.asByteArray()
  }

  def downloadReference(
      referenceStoreItem: ReferenceStoreItem,
      destinationPath: String,
      credentialsProvider: Option[AwsCredentialsProvider] = None): Unit = {

    val referencePartsCount = getReferencePartsCount(referenceStoreItem, credentialsProvider)
    val fos = new FileOutputStream(destinationPath)

    // reference store parts is 1 based
    (1 to referencePartsCount).foreach(partNumber => {
      val byteArray = getReferenceAsByteArray(referenceStoreItem, partNumber, credentialsProvider)
      fos.write(byteArray)
    })
    fos.close()
  }
}
